import logging
import os
import random
import time
import uuid
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, HTTPException, Request, Response
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from . import metrics, models, schemas
from .database import Base, SessionLocal, engine, get_db

logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))
log = logging.getLogger("ajio-ops")

REORDER_THRESHOLD = int(os.getenv("REORDER_THRESHOLD", "10"))
CARRIERS = ["Delhivery", "BlueDart", "Ecom Express", "Xpressbees"]

# Allowed order lifecycle transitions.
TRANSITIONS = {
    "PLACED": {"CONFIRMED", "CANCELLED"},
    "CONFIRMED": {"PACKED", "CANCELLED"},
    "PACKED": {"SHIPPED"},
    "SHIPPED": {"DELIVERED"},
    "DELIVERED": set(),
    "CANCELLED": set(),
}
SHIPMENT_FLOW = ["LABEL_CREATED", "PICKED_UP", "IN_TRANSIT", "OUT_FOR_DELIVERY", "DELIVERED"]

# Fault injection state (in-memory, per process) for incident simulations.
chaos = schemas.ChaosConfig()

SEED_PRODUCTS = [
    ("AJ-TSHIRT-001", "Crew Neck T-Shirt", 499.0, 120),
    ("AJ-JEANS-002", "Slim Fit Jeans", 1499.0, 60),
    ("AJ-KURTA-003", "Cotton Kurta", 999.0, 80),
    ("AJ-SNEAKER-004", "Canvas Sneakers", 1999.0, 40),
    ("AJ-JACKET-005", "Bomber Jacket", 2999.0, 15),
]


def _refresh_low_stock(db: Session):
    count = db.scalar(
        select(func.count())
        .select_from(models.Product)
        .where(models.Product.stock < REORDER_THRESHOLD)
    )
    metrics.LOW_STOCK_SKUS.set(count or 0)


@asynccontextmanager
async def lifespan(_: FastAPI):
    Base.metadata.create_all(bind=engine)
    with SessionLocal() as db:
        if db.scalar(select(func.count()).select_from(models.Product)) == 0:
            for sku, name, price, stock in SEED_PRODUCTS:
                db.add(models.Product(sku=sku, name=name, price=price, stock=stock))
            db.commit()
        _refresh_low_stock(db)
    yield


app = FastAPI(title="Ajio-style Order Management", version="1.0.0", lifespan=lifespan)


@app.middleware("http")
async def observe(request: Request, call_next):
    start = time.perf_counter()
    if chaos.latency_ms and request.url.path.startswith("/orders"):
        time.sleep(chaos.latency_ms / 1000)
    response = await call_next(request)
    route = request.scope.get("route")
    path = route.path if route else "unmatched"
    elapsed = time.perf_counter() - start
    if path != "/metrics":
        metrics.HTTP_REQUESTS.labels(request.method, path, str(response.status_code)).inc()
        metrics.HTTP_LATENCY.labels(request.method, path).observe(elapsed)
    return response


@app.get("/health")
def health(db: Session = Depends(get_db)):
    try:
        db.execute(text("SELECT 1"))
    except Exception:
        raise HTTPException(status_code=503, detail="database unavailable")
    return {"status": "ok"}


@app.get("/metrics")
def prometheus_metrics():
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)


@app.get("/inventory", response_model=list[schemas.ProductOut])
def list_inventory(db: Session = Depends(get_db)):
    return db.scalars(select(models.Product).order_by(models.Product.sku)).all()


@app.post("/inventory/restock", response_model=schemas.ProductOut)
def restock(body: schemas.RestockIn, db: Session = Depends(get_db)):
    product = db.get(models.Product, body.sku)
    if not product:
        raise HTTPException(404, f"unknown sku {body.sku}")
    product.stock += body.quantity
    db.commit()
    db.refresh(product)
    _refresh_low_stock(db)
    return product


@app.post("/orders", response_model=schemas.OrderOut, status_code=201)
def create_order(body: schemas.OrderCreate, db: Session = Depends(get_db)):
    if chaos.fail_rate and random.random() < chaos.fail_rate:
        metrics.ORDERS_FAILED.labels("chaos_injected").inc()
        log.error("order creation failed: injected fault customer=%s", body.customer_id)
        raise HTTPException(503, "order service temporarily unavailable")

    # Merge duplicate SKUs then validate stock for every line before touching it.
    wanted: dict[str, int] = {}
    for item in body.items:
        wanted[item.sku] = wanted.get(item.sku, 0) + item.quantity

    products = {}
    for sku, qty in wanted.items():
        product = db.get(models.Product, sku)
        if not product:
            metrics.ORDERS_FAILED.labels("unknown_sku").inc()
            raise HTTPException(404, f"unknown sku {sku}")
        if product.stock < qty:
            metrics.ORDERS_FAILED.labels("out_of_stock").inc()
            log.warning("out of stock sku=%s requested=%s available=%s", sku, qty, product.stock)
            raise HTTPException(409, f"insufficient stock for {sku}")
        products[sku] = product

    order = models.Order(customer_id=body.customer_id, status="PLACED")
    total = 0.0
    for sku, qty in wanted.items():
        product = products[sku]
        product.stock -= qty
        total += product.price * qty
        order.items.append(models.OrderItem(sku=sku, quantity=qty, unit_price=product.price))
    order.total = round(total, 2)
    db.add(order)
    db.commit()
    db.refresh(order)

    metrics.ORDERS_PLACED.inc()
    metrics.ORDER_STATUS_TRANSITIONS.labels("PLACED").inc()
    _refresh_low_stock(db)
    log.info("order placed id=%s total=%s", order.id, order.total)
    return order


@app.get("/orders/{order_id}", response_model=schemas.OrderOut)
def get_order(order_id: int, db: Session = Depends(get_db)):
    order = db.get(models.Order, order_id)
    if not order:
        raise HTTPException(404, "order not found")
    return order


@app.patch("/orders/{order_id}/status", response_model=schemas.OrderOut)
def update_status(order_id: int, body: schemas.StatusUpdate, db: Session = Depends(get_db)):
    order = db.get(models.Order, order_id)
    if not order:
        raise HTTPException(404, "order not found")
    target = body.status.upper()
    if target not in TRANSITIONS:
        raise HTTPException(422, f"unknown status {body.status}")
    if target not in TRANSITIONS[order.status]:
        raise HTTPException(409, f"cannot move from {order.status} to {target}")

    if target == "CANCELLED":
        # Return reserved stock to inventory.
        for item in order.items:
            db.get(models.Product, item.sku).stock += item.quantity
    order.status = target
    db.commit()
    db.refresh(order)
    metrics.ORDER_STATUS_TRANSITIONS.labels(target).inc()
    _refresh_low_stock(db)
    return order


@app.post("/orders/{order_id}/ship", response_model=schemas.ShipmentOut, status_code=201)
def assign_shipment(order_id: int, db: Session = Depends(get_db)):
    order = db.get(models.Order, order_id)
    if not order:
        raise HTTPException(404, "order not found")
    if order.status != "PACKED":
        raise HTTPException(409, "order must be PACKED before shipping")
    if order.shipment:
        raise HTTPException(409, "shipment already exists")

    carrier = CARRIERS[order.id % len(CARRIERS)]
    shipment = models.Shipment(
        order_id=order.id,
        carrier=carrier,
        tracking_number=f"AJ{uuid.uuid4().hex[:10].upper()}",
    )
    order.status = "SHIPPED"
    db.add(shipment)
    db.commit()
    db.refresh(shipment)
    metrics.SHIPMENTS_CREATED.labels(carrier).inc()
    metrics.ORDER_STATUS_TRANSITIONS.labels("SHIPPED").inc()
    return shipment


@app.get("/shipments/{tracking_number}", response_model=schemas.ShipmentOut)
def track_shipment(tracking_number: str, db: Session = Depends(get_db)):
    shipment = db.scalar(
        select(models.Shipment).where(models.Shipment.tracking_number == tracking_number)
    )
    if not shipment:
        raise HTTPException(404, "tracking number not found")
    return shipment


@app.post("/shipments/{tracking_number}/advance", response_model=schemas.ShipmentOut)
def advance_shipment(tracking_number: str, db: Session = Depends(get_db)):
    shipment = db.scalar(
        select(models.Shipment).where(models.Shipment.tracking_number == tracking_number)
    )
    if not shipment:
        raise HTTPException(404, "tracking number not found")
    idx = SHIPMENT_FLOW.index(shipment.status)
    if idx == len(SHIPMENT_FLOW) - 1:
        raise HTTPException(409, "shipment already delivered")
    shipment.status = SHIPMENT_FLOW[idx + 1]
    if shipment.status == "DELIVERED":
        shipment.order.status = "DELIVERED"
        metrics.ORDER_STATUS_TRANSITIONS.labels("DELIVERED").inc()
    db.commit()
    db.refresh(shipment)
    return shipment


@app.post("/chaos", response_model=schemas.ChaosConfig)
def set_chaos(config: schemas.ChaosConfig):
    """Inject failures/latency into order endpoints to simulate incidents."""
    global chaos
    chaos = config
    log.warning("chaos config set: %s", config.model_dump())
    return chaos
