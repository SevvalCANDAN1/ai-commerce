from typing import List

from beanie import Document
from pydantic import BaseModel, Field
from pymongo import IndexModel


class Variant(BaseModel):
    """
    Embedded document for product variants (e.g., Color, Size).
    """
    sku: str = Field(..., description="Stock Keeping Unit - Unique identifier for the variant")
    color: str | None = None
    size: str | None = None
    stock: int = Field(default=0, ge=0, description="Available stock quantity for this variant")
    price_override: float | None = Field(default=None, description="Override base price if this variant costs more/less")

class Product(Document):
    """
    Main product document.
    """
    name: str = Field(..., max_length=150)
    description: str
    base_price: float = Field(..., gt=0)
    
    # Array of categories for fast indexing (e.g., ["Clothing", "Men", "T-Shirts"])
    categories: List[str] = []
    
    # Embedded list of variants
    variants: List[Variant] = []
    
    # Status for soft delete and visibility control ("draft", "published", "deleted")
    status: str = Field(default="draft")
    
    # Automatically calculated sum of all variant stocks
    total_stock: int = Field(default=0, ge=0)

    class Settings:
        name = "products"
        indexes = [
            IndexModel([("status", 1), ("total_stock", 1)], name="storefront_visibility_idx"),
        ]
