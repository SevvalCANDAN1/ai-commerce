from bson import ObjectId
from fastapi import HTTPException, status

from app.core.deps import CartOwner
from app.core.storefront import is_storefront_visible
from app.models.cart import Cart, CartItem
from app.models.product import Product, Variant
from app.models.user import User
from app.routers.product import get_product_or_404
from app.schemas.cart import CartLineResponse, CartResponse
from app.services.pricing_service import calculate_cart_pricing, get_unit_price


def get_variant_or_404(product: Product, variant_sku: str) -> Variant:
    for variant in product.variants:
        if variant.sku == variant_sku:
            return variant
    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail="Variant not found",
    )


async def get_or_create_cart_for_owner(owner: CartOwner) -> Cart:
    if owner.user is not None:
        cart = await Cart.find_one(Cart.user_id == owner.user.id)
        if cart is None:
            cart = Cart(user_id=owner.user.id, guest_id=None, items=[])
            await cart.insert()
        return cart

    cart = await Cart.find_one(Cart.guest_id == owner.guest_id)
    if cart is None:
        cart = Cart(user_id=None, guest_id=owner.guest_id, items=[])
        await cart.insert()
    return cart


async def get_user_cart(user: User) -> Cart:
    return await get_or_create_cart_for_owner(CartOwner(user=user))


def find_cart_item_index(cart: Cart, product_id: ObjectId, variant_sku: str) -> int | None:
    for index, item in enumerate(cart.items):
        if item.product_id == product_id and item.variant_sku == variant_sku:
            return index
    return None


async def validate_cart_product(product_id: str) -> Product:
    product = await get_product_or_404(product_id)
    if not is_storefront_visible(product):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Product not found",
        )
    return product


async def build_cart_response(cart: Cart, coupon_code: str | None = None) -> CartResponse:
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

    pricing = calculate_cart_pricing(subtotal=subtotal, coupon_code=coupon_code)

    return CartResponse(
        id=str(cart.id),
        guest_id=cart.guest_id,
        items=lines,
        item_count=item_count,
        subtotal=pricing.subtotal,
        tax_amount=pricing.tax_amount,
        shipping_amount=pricing.shipping_amount,
        discount_amount=pricing.discount_amount,
        grand_total=pricing.grand_total,
    )


async def merge_guest_cart_into_user(user: User, guest_id: str) -> Cart:
    user_cart = await get_user_cart(user)
    guest_cart = await Cart.find_one(Cart.guest_id == guest_id)

    if guest_cart is None or not guest_cart.items:
        return user_cart

    for guest_item in guest_cart.items:
        product = await Product.get(guest_item.product_id)
        if product is None or not is_storefront_visible(product):
            continue

        try:
            variant = get_variant_or_404(product, guest_item.variant_sku)
        except HTTPException:
            continue

        existing_index = find_cart_item_index(
            user_cart, guest_item.product_id, guest_item.variant_sku
        )
        merged_quantity = (
            user_cart.items[existing_index].quantity + guest_item.quantity
            if existing_index is not None
            else guest_item.quantity
        )
        merged_quantity = min(merged_quantity, variant.stock)

        if existing_index is not None:
            if merged_quantity <= 0:
                user_cart.items.pop(existing_index)
            else:
                user_cart.items[existing_index].quantity = merged_quantity
        elif merged_quantity > 0:
            user_cart.items.append(
                CartItem(
                    product_id=guest_item.product_id,
                    variant_sku=guest_item.variant_sku,
                    quantity=merged_quantity,
                )
            )

    await user_cart.save()
    await guest_cart.delete()
    return user_cart
