def place(client, sku="AJ-TSHIRT-001", qty=2, customer="cust-1"):
    return client.post(
        "/orders", json={"customer_id": customer, "items": [{"sku": sku, "quantity": qty}]}
    )


def stock_of(client, sku):
    return next(p["stock"] for p in client.get("/inventory").json() if p["sku"] == sku)


def test_health(client):
    assert client.get("/health").json() == {"status": "ok"}


def test_inventory_seeded(client):
    assert len(client.get("/inventory").json()) == 5


def test_create_order_decrements_stock_and_totals(client):
    before = stock_of(client, "AJ-TSHIRT-001")
    r = place(client, qty=3)
    assert r.status_code == 201
    body = r.json()
    assert body["status"] == "PLACED"
    assert body["total"] == 499.0 * 3
    assert stock_of(client, "AJ-TSHIRT-001") == before - 3


def test_duplicate_skus_are_merged(client):
    r = client.post(
        "/orders",
        json={
            "customer_id": "c",
            "items": [
                {"sku": "AJ-JEANS-002", "quantity": 1},
                {"sku": "AJ-JEANS-002", "quantity": 2},
            ],
        },
    )
    assert r.status_code == 201
    assert r.json()["items"][0]["quantity"] == 3


def test_out_of_stock_rejected_and_stock_untouched(client):
    before = stock_of(client, "AJ-JACKET-005")
    r = client.post(
        "/orders",
        json={"customer_id": "c", "items": [
            {"sku": "AJ-TSHIRT-001", "quantity": 1},
            {"sku": "AJ-JACKET-005", "quantity": 16},
        ]},
    )
    # quantity 16 is within schema limit (20) but exceeds stock of 15
    assert r.status_code == 409
    assert stock_of(client, "AJ-JACKET-005") == before


def test_unknown_sku(client):
    assert place(client, sku="NOPE").status_code == 404


def test_validation_error(client):
    r = client.post("/orders", json={"customer_id": "c", "items": []})
    assert r.status_code == 422


def test_get_order_not_found(client):
    assert client.get("/orders/9999").status_code == 404


def test_full_lifecycle_to_delivery(client):
    oid = place(client).json()["id"]
    for status in ("CONFIRMED", "PACKED"):
        assert client.patch(f"/orders/{oid}/status", json={"status": status}).status_code == 200
    ship = client.post(f"/orders/{oid}/ship")
    assert ship.status_code == 201
    tracking = ship.json()["tracking_number"]
    assert client.get(f"/orders/{oid}").json()["status"] == "SHIPPED"

    for _ in range(4):
        assert client.post(f"/shipments/{tracking}/advance").status_code == 200
    assert client.get(f"/shipments/{tracking}").json()["status"] == "DELIVERED"
    assert client.get(f"/orders/{oid}").json()["status"] == "DELIVERED"
    assert client.post(f"/shipments/{tracking}/advance").status_code == 409


def test_cannot_ship_unpacked_order(client):
    oid = place(client).json()["id"]
    assert client.post(f"/orders/{oid}/ship").status_code == 409


def test_invalid_transition_rejected(client):
    oid = place(client).json()["id"]
    r = client.patch(f"/orders/{oid}/status", json={"status": "DELIVERED"})
    assert r.status_code == 409


def test_cancel_returns_stock(client):
    before = stock_of(client, "AJ-TSHIRT-001")
    oid = place(client, qty=4).json()["id"]
    assert stock_of(client, "AJ-TSHIRT-001") == before - 4
    client.patch(f"/orders/{oid}/status", json={"status": "CANCELLED"})
    assert stock_of(client, "AJ-TSHIRT-001") == before


def test_restock(client):
    before = stock_of(client, "AJ-SNEAKER-004")
    r = client.post("/inventory/restock", json={"sku": "AJ-SNEAKER-004", "quantity": 25})
    assert r.status_code == 200
    assert stock_of(client, "AJ-SNEAKER-004") == before + 25


def test_unknown_tracking_number(client):
    assert client.get("/shipments/DOESNOTEXIST").status_code == 404
