"""Modular cart pricing: subtotal → tax → shipping → coupon → grand total."""

from dataclasses import dataclass

from app.config import settings


@dataclass
class CartPricing:
    """Breakdown of all cart totals returned to the client."""

    subtotal: float
    tax_amount: float
    shipping_amount: float
    discount_amount: float
    grand_total: float


# Prototype coupon map: code -> discount rate (0.10 = 10% off subtotal)
COUPON_DISCOUNT_RATES: dict[str, float] = {
    "WELCOME10": 0.10,
}


def get_unit_price(product, variant) -> float:
    """Unit price always comes from the product catalog, never from the client."""
    if variant.price_override is not None:
        return variant.price_override
    return product.base_price


def calculate_discount(subtotal: float, coupon_code: str | None) -> float:
    """Applies a percentage coupon discount when the code is valid."""
    if not coupon_code:
        return 0.0

    discount_rate = COUPON_DISCOUNT_RATES.get(coupon_code.upper())
    if discount_rate is None:
        return 0.0

    return round(subtotal * discount_rate, 2)


def calculate_shipping(subtotal: float) -> float:
    """Free shipping when subtotal meets the configured threshold."""
    if subtotal >= settings.free_shipping_threshold:
        return 0.0
    return settings.shipping_flat_rate


def calculate_tax(subtotal: float) -> float:
    """Simple tax calculation applied to the merchandise subtotal."""
    return round(subtotal * settings.tax_rate, 2)


def calculate_cart_pricing(subtotal: float, coupon_code: str | None = None) -> CartPricing:
    """
    Full pricing chain requested by Modül 1:
    subtotal → tax + shipping - coupon discount → grand_total
    """
    tax_amount = calculate_tax(subtotal)
    shipping_amount = calculate_shipping(subtotal)
    discount_amount = calculate_discount(subtotal, coupon_code)
    grand_total = subtotal + tax_amount + shipping_amount - discount_amount

    return CartPricing(
        subtotal=round(subtotal, 2),
        tax_amount=tax_amount,
        shipping_amount=shipping_amount,
        discount_amount=discount_amount,
        grand_total=round(grand_total, 2),
    )
