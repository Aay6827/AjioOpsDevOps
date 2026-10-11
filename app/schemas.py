from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class ProductOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    sku: str
    name: str
    price: float
    stock: int
    warehouse: str


class RestockIn(BaseModel):
    sku: str
    quantity: int = Field(gt=0)


class OrderItemIn(BaseModel):
    sku: str
    quantity: int = Field(gt=0, le=20)


class OrderCreate(BaseModel):
    customer_id: str = Field(min_length=1)
    items: list[OrderItemIn] = Field(min_length=1)


class OrderItemOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    sku: str
    quantity: int
    unit_price: float


class ShipmentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    carrier: str
    tracking_number: str
    status: str


class OrderOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    customer_id: str
    status: str
    total: float
    created_at: datetime
    items: list[OrderItemOut]
    shipment: ShipmentOut | None = None


class StatusUpdate(BaseModel):
    status: str


class ChaosConfig(BaseModel):
    """Fault injection used to simulate incidents for RCA exercises."""

    fail_rate: float = Field(default=0.0, ge=0.0, le=1.0)
    latency_ms: int = Field(default=0, ge=0, le=5000)
