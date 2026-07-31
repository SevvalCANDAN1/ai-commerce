"""Shared storefront visibility rules for customer-facing product queries."""

from app.models.product import Product


def is_storefront_visible(product: Product) -> bool:
    """True when a product may be shown or purchased on the public storefront."""
    return product.status == "published" and product.total_stock > 0


def storefront_filters(category: str | None = None) -> list:
    """
    Base MongoDB filters for every customer-facing product listing.
    Modül 1: visibility rules live in one place instead of being duplicated.
    """
    filters = [
        Product.status == "published",
        Product.total_stock > 0,
    ]

    if category:
        filters.append(Product.categories == category)

    return filters
