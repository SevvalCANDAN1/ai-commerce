from datetime import datetime

from beanie import Document, PydanticObjectId
from pymongo import IndexModel

from app.models.order import AddressSnapshot, OrderItemSnapshot, PricingSnapshot


class CheckoutSession(Document):
    """Temporary checkout snapshot validated before payment."""

    user_id: PydanticObjectId
    address_snapshot: AddressSnapshot
    items_snapshot: list[OrderItemSnapshot]
    pricing_snapshot: PricingSnapshot
    coupon_code: str | None = None
    expires_at: datetime
    consumed: bool = False

    class Settings:
        name = "checkout_sessions"
        indexes = [
            IndexModel([("expires_at", 1)], expireAfterSeconds=0),
        ]
