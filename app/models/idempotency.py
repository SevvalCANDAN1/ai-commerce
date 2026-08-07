from datetime import datetime

from beanie import Document, Indexed, PydanticObjectId
from pymongo import IndexModel


class StockReservation(Document):
    """Short-lived stock lock during checkout."""

    user_id: PydanticObjectId
    checkout_session_id: PydanticObjectId
    product_id: PydanticObjectId
    variant_sku: str
    quantity: int
    expires_at: datetime
    released: bool = False

    class Settings:
        name = "stock_reservations"
        indexes = [
            IndexModel([("expires_at", 1)], expireAfterSeconds=0),
        ]


class IdempotencyRecord(Document):
    """Stores prior payment responses for duplicate request protection."""

    key: Indexed(str, unique=True)
    endpoint: str
    response_body: dict
    status_code: int
    created_at: datetime

    class Settings:
        name = "idempotency_records"
