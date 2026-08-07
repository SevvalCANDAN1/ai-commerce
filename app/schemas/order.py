from datetime import datetime

from pydantic import BaseModel, Field

from app.models.order import (
    AddressSnapshot,
    OrderItemSnapshot,
    OrderStatus,
    PricingSnapshot,
    StatusHistoryEntry,
)


class OrderResponse(BaseModel):
    id: str
    order_number: str
    user_id: str
    items_snapshot: list[OrderItemSnapshot]
    address_snapshot: AddressSnapshot
    pricing_snapshot: PricingSnapshot
    status: OrderStatus
    status_history: list[StatusHistoryEntry]
    payment_id: str | None
    coupon_code: str | None


class OrderStatusUpdateRequest(BaseModel):
    status: OrderStatus
    note: str | None = Field(default=None, max_length=500)


class OrderListResponse(BaseModel):
    items: list[OrderResponse]
    total: int
    page: int
    page_size: int
