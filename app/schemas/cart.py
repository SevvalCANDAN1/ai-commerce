from pydantic import BaseModel, Field


class CartItemAddRequest(BaseModel):
    """Request body for adding a product variant to the cart."""

    product_id: str = Field(..., min_length=1)
    variant_sku: str = Field(..., min_length=1)
    quantity: int = Field(default=1, ge=1)


class CartItemUpdateRequest(BaseModel):
    """Request body for updating quantity of an existing cart line."""

    product_id: str = Field(..., min_length=1)
    variant_sku: str = Field(..., min_length=1)
    quantity: int = Field(..., ge=1)


class CartItemRemoveRequest(BaseModel):
    """Request body for removing a line from the cart."""

    product_id: str = Field(..., min_length=1)
    variant_sku: str = Field(..., min_length=1)


class CartLineResponse(BaseModel):
    """A cart line with prices loaded from the product catalog."""

    product_id: str
    variant_sku: str
    product_name: str
    quantity: int
    unit_price: float
    line_total: float


class CartResponse(BaseModel):
    """Full cart summary for the authenticated user."""

    id: str
    items: list[CartLineResponse]
    item_count: int
    subtotal: float
