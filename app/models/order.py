from datetime import datetime
from enum import StrEnum

from beanie import Document, Indexed, PydanticObjectId
from pydantic import BaseModel, Field


class OrderStatus(StrEnum):
    PENDING = "pending"
    CONFIRMED = "confirmed"
    SHIPPED = "shipped"
    DELIVERED = "delivered"
    CANCELLED = "cancelled"


ALLOWED_ORDER_TRANSITIONS: dict[OrderStatus, set[OrderStatus]] = {
    OrderStatus.PENDING: {OrderStatus.CONFIRMED, OrderStatus.CANCELLED},
    OrderStatus.CONFIRMED: {OrderStatus.SHIPPED, OrderStatus.CANCELLED},
    OrderStatus.SHIPPED: {OrderStatus.DELIVERED},
    OrderStatus.DELIVERED: set(),
    OrderStatus.CANCELLED: set(),
}


class OrderItemSnapshot(BaseModel):
    product_id: str
    variant_sku: str
    product_name: str
    quantity: int
    unit_price: float
    line_total: float


class AddressSnapshot(BaseModel):
    title: str
    city: str
    country: str
    full_address: str
    zip_code: str | None = None


class PricingSnapshot(BaseModel):
    subtotal: float
    tax_amount: float
    shipping_amount: float
    discount_amount: float
    grand_total: float


class StatusHistoryEntry(BaseModel):
    status: OrderStatus
    changed_at: datetime
    changed_by: str
    note: str | None = None


class Order(Document):
    order_number: Indexed(str, unique=True)
    user_id: PydanticObjectId
    items_snapshot: list[OrderItemSnapshot]
    address_snapshot: AddressSnapshot
    pricing_snapshot: PricingSnapshot
    status: OrderStatus = OrderStatus.PENDING
    status_history: list[StatusHistoryEntry] = Field(default_factory=list)
    payment_id: str | None = None
    coupon_code: str | None = None

    class Settings:
        name = "orders"
