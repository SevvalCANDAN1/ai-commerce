from beanie import Document, Indexed, PydanticObjectId
from pydantic import BaseModel, Field
from pymongo import IndexModel


class CartItem(BaseModel):
    """Single line in the cart — references product data, does not copy it."""

    product_id: PydanticObjectId
    variant_sku: str = Field(..., min_length=1)
    quantity: int = Field(default=1, ge=1)


class Cart(Document):
    """Active cart for a logged-in user or a guest session."""

    user_id: PydanticObjectId | None = None
    guest_id: str | None = None
    items: list[CartItem] = []

    class Settings:
        name = "carts"
        indexes = [
            IndexModel(
                [("user_id", 1)],
                unique=True,
                partialFilterExpression={"user_id": {"$type": "objectId"}},
                name="unique_user_cart",
            ),
            IndexModel(
                [("guest_id", 1)],
                unique=True,
                partialFilterExpression={"guest_id": {"$type": "string"}},
                name="unique_guest_cart",
            ),
        ]
