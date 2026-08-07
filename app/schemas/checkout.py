from datetime import datetime

from pydantic import BaseModel, Field

from app.models.order import AddressSnapshot, OrderItemSnapshot, PricingSnapshot


class CheckoutPreviewRequest(BaseModel):
    address_index: int = Field(..., ge=0)
    coupon_code: str | None = Field(default=None, min_length=1)


class CheckoutSessionResponse(BaseModel):
    id: str
    address_snapshot: AddressSnapshot
    items_snapshot: list[OrderItemSnapshot]
    pricing_snapshot: PricingSnapshot
    coupon_code: str | None
    expires_at: datetime
    consumed: bool
