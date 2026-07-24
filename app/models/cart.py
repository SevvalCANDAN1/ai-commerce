from beanie import Document, Indexed, PydanticObjectId
from pydantic import BaseModel, Field


class CartItem(BaseModel):
    """Single line in the cart — references product data, does not copy it."""

    product_id: PydanticObjectId
    variant_sku: str = Field(..., min_length=1)
    quantity: int = Field(default=1, ge=1)


class Cart(Document):
    """One active cart per logged-in user."""

    user_id: Indexed(PydanticObjectId, unique=True)
    items: list[CartItem] = []

    class Settings:
        name = "carts"