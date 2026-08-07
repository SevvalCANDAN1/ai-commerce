from bson import ObjectId
from bson.errors import InvalidId
from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.core.deps import CartOwner, resolve_cart_owner
from app.core.security import get_current_user
from app.models.cart import CartItem
from app.models.user import User
from app.schemas.cart import (
    CartItemAddRequest,
    CartItemRemoveRequest,
    CartItemUpdateRequest,
    CartMergeRequest,
    CartResponse,
)
from app.services.cart_service import (
    build_cart_response,
    find_cart_item_index,
    get_or_create_cart_for_owner,
    get_variant_or_404,
    merge_guest_cart_into_user,
    validate_cart_product,
)

router = APIRouter(
    prefix="/cart",
    tags=["Cart"],
)


@router.get("/", response_model=CartResponse)
async def get_cart(
    coupon: str | None = Query(default=None, min_length=1),
    owner: CartOwner = Depends(resolve_cart_owner),
):
    """Return the current cart (authenticated user or guest via X-Guest-Id)."""
    cart = await get_or_create_cart_for_owner(owner)
    return await build_cart_response(cart, coupon_code=coupon)


@router.post("/merge", response_model=CartResponse)
async def merge_cart(
    request: CartMergeRequest,
    current_user: User = Depends(get_current_user),
):
    """Merge a guest cart into the authenticated user's cart after login."""
    cart = await merge_guest_cart_into_user(current_user, request.guest_id)
    return await build_cart_response(cart)


@router.post("/items", response_model=CartResponse, status_code=status.HTTP_201_CREATED)
async def add_cart_item(
    request: CartItemAddRequest,
    coupon: str | None = Query(default=None, min_length=1),
    owner: CartOwner = Depends(resolve_cart_owner),
):
    """Add a product variant to the cart or increase quantity if it already exists."""
    product = await validate_cart_product(request.product_id)
    variant = get_variant_or_404(product, request.variant_sku)

    try:
        product_object_id = ObjectId(request.product_id)
    except InvalidId:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Product not found",
        )

    cart = await get_or_create_cart_for_owner(owner)
    existing_index = find_cart_item_index(cart, product_object_id, request.variant_sku)
    new_quantity = (
        cart.items[existing_index].quantity + request.quantity
        if existing_index is not None
        else request.quantity
    )

    if new_quantity > variant.stock:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Insufficient stock. Only {variant.stock} available.",
        )

    if existing_index is not None:
        cart.items[existing_index].quantity = new_quantity
    else:
        cart.items.append(
            CartItem(
                product_id=product_object_id,
                variant_sku=request.variant_sku,
                quantity=request.quantity,
            )
        )

    await cart.save()
    return await build_cart_response(cart, coupon_code=coupon)


@router.put("/items", response_model=CartResponse)
async def update_cart_item(
    request: CartItemUpdateRequest,
    coupon: str | None = Query(default=None, min_length=1),
    owner: CartOwner = Depends(resolve_cart_owner),
):
    """Update quantity for an existing cart line."""
    product = await validate_cart_product(request.product_id)
    variant = get_variant_or_404(product, request.variant_sku)

    try:
        product_object_id = ObjectId(request.product_id)
    except InvalidId:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Product not found",
        )

    cart = await get_or_create_cart_for_owner(owner)
    existing_index = find_cart_item_index(cart, product_object_id, request.variant_sku)
    if existing_index is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Item not found in cart",
        )

    if request.quantity > variant.stock:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Insufficient stock. Only {variant.stock} available.",
        )

    cart.items[existing_index].quantity = request.quantity
    await cart.save()
    return await build_cart_response(cart, coupon_code=coupon)


@router.delete("/items", response_model=CartResponse)
async def remove_cart_item(
    request: CartItemRemoveRequest,
    coupon: str | None = Query(default=None, min_length=1),
    owner: CartOwner = Depends(resolve_cart_owner),
):
    """Remove a product variant from the cart."""
    try:
        product_object_id = ObjectId(request.product_id)
    except InvalidId:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Product not found",
        )

    cart = await get_or_create_cart_for_owner(owner)
    existing_index = find_cart_item_index(cart, product_object_id, request.variant_sku)
    if existing_index is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Item not found in cart",
        )

    cart.items.pop(existing_index)
    await cart.save()
    return await build_cart_response(cart, coupon_code=coupon)
