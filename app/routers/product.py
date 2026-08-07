from typing import List

from bson import ObjectId
from bson.errors import InvalidId
from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.core.security import get_current_store_admin
from app.core.storefront import is_storefront_visible, storefront_filters
from app.models.product import Product
from app.models.user import User
from app.schemas.product import (
    ProductCreateRequest,
    ProductResponse,
    ProductUpdateRequest,
    calculate_total_stock,
    product_to_response,
)
from app.services.embedding_service import refresh_product_embedding

router = APIRouter(
    prefix="/products",
    tags=["Products"],
)

ALLOWED_PRODUCT_STATUSES = {"draft", "published", "deleted"}


async def get_product_or_404(product_id: str) -> Product:
    """Fetches a product by ID or raises 404 for invalid/missing IDs."""
    try:
        product = await Product.get(ObjectId(product_id))
    except InvalidId:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Product not found",
        )

    if product is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Product not found",
        )

    return product


@router.post("/", status_code=status.HTTP_201_CREATED, response_model=ProductResponse)
async def create_product(
    request: ProductCreateRequest,
    current_admin: User = Depends(get_current_store_admin),
):
    """Create a new product. Only accessible by superusers."""
    new_product = Product(
        name=request.name,
        description=request.description,
        base_price=request.base_price,
        categories=request.categories,
        variants=request.variants,
        status="published",
        total_stock=calculate_total_stock(request.variants),
    )
    await new_product.insert()
    await refresh_product_embedding(new_product)

    return product_to_response(new_product)


@router.get("/", response_model=List[ProductResponse])
async def list_products(
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=20, ge=1, le=100),
    category: str | None = Query(default=None, min_length=1),
):
    """
    Public endpoint to list products (Storefront).
    Only returns published products with available stock.
    """
    filters = storefront_filters(category=category)

    products = await Product.find(*filters).skip(skip).limit(limit).to_list()
    return [product_to_response(product) for product in products]


@router.get("/{product_id}", response_model=ProductResponse)
async def get_product(product_id: str):
    """Public endpoint to fetch a single visible product by ID."""
    product = await get_product_or_404(product_id)

    if not is_storefront_visible(product):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Product not found",
        )

    return product_to_response(product)


@router.put("/{product_id}", response_model=ProductResponse)
async def update_product(
    product_id: str,
    request: ProductUpdateRequest,
    current_admin: User = Depends(get_current_store_admin),
):
    """Update an existing product. Only accessible by superusers."""
    product = await get_product_or_404(product_id)
    update_data = request.model_dump(exclude_unset=True)

    if not update_data:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No fields provided for update",
        )

    if "status" in update_data and update_data["status"] not in ALLOWED_PRODUCT_STATUSES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Status must be one of: {', '.join(sorted(ALLOWED_PRODUCT_STATUSES))}",
        )

    if "variants" in update_data:
        update_data["total_stock"] = calculate_total_stock(update_data["variants"])

    for field, value in update_data.items():
        setattr(product, field, value)

    await product.save()
    await refresh_product_embedding(product)
    return product_to_response(product)


@router.delete("/{product_id}", response_model=ProductResponse)
async def delete_product(
    product_id: str,
    current_admin: User = Depends(get_current_store_admin),
):
    """Soft-delete a product by setting its status to deleted."""
    product = await get_product_or_404(product_id)
    product.status = "deleted"
    await product.save()

    return product_to_response(product)
