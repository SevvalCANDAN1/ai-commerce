"""Shared late-delivery feature column lists."""

NUMERIC = [
    "estimated_days",
    "purchase_hour",
    "purchase_dow",
    "purchase_month",
    "n_items",
    "n_sellers",
    "n_products",
    "total_price",
    "total_freight",
    "avg_price",
    "avg_freight",
    "product_weight_g",
    "product_photos_qty",
    "n_payments",
    "payment_value",
    "payment_installments",
    "same_state",
    "seller_prior_orders",
    "seller_prior_late_rate",
]

CATEGORICAL = [
    "customer_state",
    "seller_state",
    "category",
    "payment_type",
]
