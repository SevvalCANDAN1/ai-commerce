from typing import List

from pydantic import BaseModel, Field

from app.models.product import Product, Variant


class ProductCreateRequest(BaseModel):
    """Input schema for creating a new product."""

    name: str = Field(..., max_length=150)
    description: str
    base_price: float = Field(..., gt=0)
    categories: List[str] = []
    variants: List[Variant] = []


class ProductUpdateRequest(BaseModel):
    """Input schema for partially updating a product."""

    name: str | None = Field(default=None, max_length=150)
    description: str | None = None
    base_price: float | None = Field(default=None, gt=0)
    categories: List[str] | None = None
    variants: List[Variant] | None = None
    status: str | None = Field(
        default=None,
        description='Product visibility status: "draft", "published", or "deleted"',
    )


class ProductResponse(BaseModel):
    """Output schema for returning product data to the client."""

    id: str
    name: str
    description: str
    base_price: float
    categories: List[str]
    variants: List[Variant]
    status: str
    total_stock: int

    class Config:
        from_attributes = True


def product_to_response(product: Product) -> ProductResponse:
    """Maps a Beanie Product document to the public API response schema."""
    return ProductResponse(
        id=str(product.id),
        name=product.name,
        description=product.description,
        base_price=product.base_price,
        categories=product.categories,
        variants=product.variants,
        status=product.status,
        total_stock=product.total_stock,
    )


def calculate_total_stock(variants: List[Variant]) -> int:
    """Sums variant stock quantities for the product-level total_stock field."""
    return sum(variant.stock for variant in variants)
