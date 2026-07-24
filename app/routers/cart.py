from bson import ObjectId
from bson.errors import InvalidId
from fastapi import APIRouter, Depends, HTTPException, status

from app.core.security import get_current_user
from app.models.cart import Cart, CartItem
from app.models.product import Product, Variant
from app.models.user import User
from app.routers.product import get_product_or_404, is_storefront_visible
from app.schemas.cart import (
    CartItemAddRequest,
    CartItemRemoveRequest,
    CartItemUpdateRequest,
    CartLineResponse,
    CartResponse,
)

router = APIRouter(
    prefix="/cart",
    tags=["Cart"],
)


def get_variant_or_404(product: Product, variant_sku: str) -> Variant:
    """Finds a variant by SKU or raises 404."""
    for variant in product.variants:
        if variant.sku == variant_sku:
            return variant
    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail="Variant not found",
    )


def get_unit_price(product: Product, variant: Variant) -> float:
    """Calculates unit price from the database (never trust client prices)."""
    if variant.price_override is not None:
        return variant.price_override
    return product.base_price


async def get_or_create_cart(user: User) -> Cart:
    """Returns the user's cart, creating an empty one if needed."""
    cart = await Cart.find_one(Cart.user_id == user.id)
    if cart is None:
        cart = Cart(user_id=user.id, items=[])
        await cart.insert()
    return cart


def find_cart_item_index(cart: Cart, product_id: ObjectId, variant_sku: str) -> int | None:
    """Returns the index of a matching cart line, or None if not found."""
    for index, item in enumerate(cart.items):
        if item.product_id == product_id and item.variant_sku == variant_sku:
            return index
    return None


async def validate_cart_product(product_id: str) -> Product:
    """Loads a product and ensures it can be purchased on the storefront."""
    product = await get_product_or_404(product_id)
    if not is_storefront_visible(product):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Product not found",
        )
    return product


async def build_cart_response(cart: Cart) -> CartResponse:
    """Builds API response with live prices and totals from the product catalog."""
    lines: list[CartLineResponse] = []
    subtotal = 0.0
    item_count = 0

    for item in cart.items:
        product = await Product.get(item.product_id)
        if product is None or not is_storefront_visible(product):
            continue

        try:
            variant = get_variant_or_404(product, item.variant_sku)
        except HTTPException:
            continue

        unit_price = get_unit_price(product, variant)
        line_total = unit_price * item.quantity
        subtotal += line_total
        item_count += item.quantity

        lines.append(
            CartLineResponse(
                product_id=str(item.product_id),
                variant_sku=item.variant_sku,
                product_name=product.name,
                quantity=item.quantity,
                unit_price=unit_price,
                line_total=line_total,
            )
        )

    return CartResponse(
        id=str(cart.id),
        items=lines,
        item_count=item_count,
        subtotal=subtotal,
    )


@router.get("/", response_model=CartResponse)
async def get_cart(current_user: User = Depends(get_current_user)):
    """Return the current user's cart with prices calculated from the database."""
    cart = await get_or_create_cart(current_user)
    return await build_cart_response(cart)


@router.post("/items", response_model=CartResponse, status_code=status.HTTP_201_CREATED)
async def add_cart_item(
    request: CartItemAddRequest,
    current_user: User = Depends(get_current_user),
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

    cart = await get_or_create_cart(current_user)
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
    return await build_cart_response(cart)


@router.put("/items", response_model=CartResponse)
async def update_cart_item(
    request: CartItemUpdateRequest,
    current_user: User = Depends(get_current_user),
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

    cart = await get_or_create_cart(current_user)
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
    return await build_cart_response(cart)


@router.delete("/items", response_model=CartResponse)
async def remove_cart_item(
    request: CartItemRemoveRequest,
    current_user: User = Depends(get_current_user),
):
    """Remove a product variant from the cart."""
    try:
        product_object_id = ObjectId(request.product_id)
    except InvalidId:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Product not found",
        )

    cart = await get_or_create_cart(current_user)
    existing_index = find_cart_item_index(cart, product_object_id, request.variant_sku)
    if existing_index is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Item not found in cart",
        )

    cart.items.pop(existing_index)
    await cart.save()
    return await build_cart_response(cart)
