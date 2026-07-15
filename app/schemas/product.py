from pydantic import BaseModel, Field
from typing import List
from app.models.product import Variant

class ProductCreateRequest(BaseModel):
    """
    Input schema for creating a new product.
    Only authorized admins can send this request.
    """
    name: str = Field(..., max_length=150)
    description: str
    base_price: float = Field(..., gt=0)
    categories: List[str] = []
    variants: List[Variant] = []
    
    # We don't ask for 'status' or 'total_stock' here, 
    # the system will handle them automatically!

class ProductResponse(BaseModel):
    """
    Output schema for returning product data to the client.
    """
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
