from fastapi import APIRouter, status, Depends
from app.models.user import User
from app.models.product import Product
from app.schemas.product import ProductCreateRequest, ProductResponse
from app.core.security import get_current_superuser
from typing import List

router = APIRouter(
    prefix="/products",
    tags=["Products"]
)

@router.post("/", status_code=status.HTTP_201_CREATED, response_model=ProductResponse)
async def create_product(
    request: ProductCreateRequest, 
    current_admin: User = Depends(get_current_superuser)
):
    """
    Create a new product.
    Only accessible by superusers (admins).
    Calculates total stock automatically from variants.
    """
    # 1. Calculate total stock by summing up variant stocks
    calculated_total_stock = 0
    for variant in request.variants:
        calculated_total_stock += variant.stock

    # 2. Create the Product document object to be saved
    new_product = Product(
        name=request.name,
        description=request.description,
        base_price=request.base_price,
        categories=request.categories,
        variants=request.variants,
        status="published", # New products are published by default
        total_stock=calculated_total_stock # Override with our calculated stock
    )

    # 3. Save to database
    await new_product.insert()

    # 4. Return the response to the client
    return ProductResponse(
        id=str(new_product.id),
        name=new_product.name,
        description=new_product.description,
        base_price=new_product.base_price,
        categories=new_product.categories,
        variants=new_product.variants,
        status=new_product.status,
        total_stock=new_product.total_stock
    )

@router.get("/", response_model=List[ProductResponse])
async def list_products(
    skip: int = 0, 
    limit: int = 20
):
    """
    Public endpoint to list products (Storefront).
    Implements Smart Visibility:
    - Only shows products that are "published"
    - Only shows products that have total_stock > 0
    Implements pagination using skip and limit.
    """
    
    raw_products = await Product.find(
        Product.status == "published",
        Product.total_stock > 0
    ).skip(skip).limit(limit).to_list()
    

    formatted_products = []
    for p in raw_products:
        formatted_products.append(
            ProductResponse(
                id=str(p.id),
                name=p.name,
                description=p.description,
                base_price=p.base_price,
                categories=p.categories,
                variants=p.variants,
                status=p.status,
                total_stock=p.total_stock
            )
        )

    return formatted_products
