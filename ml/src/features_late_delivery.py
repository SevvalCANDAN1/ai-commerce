"""Build an order-level late-delivery dataset (leakage-aware).

Target: late = delivered_customer_date > estimated_delivery_date

Only features that could be known around purchase / estimate time are used.
Actual delivery timestamps are labels only, never features.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from ml.src.paths import PROCESSED_DIR, raw_path


def _load_frames() -> dict[str, pd.DataFrame]:
    orders = pd.read_csv(
        raw_path("orders"),
        parse_dates=[
            "order_purchase_timestamp",
            "order_estimated_delivery_date",
            "order_delivered_customer_date",
        ],
    )
    return {
        "orders": orders,
        "items": pd.read_csv(raw_path("order_items")),
        "customers": pd.read_csv(raw_path("customers")),
        "sellers": pd.read_csv(raw_path("sellers")),
        "products": pd.read_csv(raw_path("products")),
        "payments": pd.read_csv(raw_path("order_payments")),
        "categories": pd.read_csv(raw_path("category_translation")),
    }


def _aggregate_items(items: pd.DataFrame, products: pd.DataFrame, categories: pd.DataFrame) -> pd.DataFrame:
    products = products.merge(categories, on="product_category_name", how="left")
    items = items.merge(products, on="product_id", how="left")

    def top_category(series: pd.Series) -> str:
        mode = series.dropna().mode()
        return mode.iloc[0] if len(mode) else "unknown"

    agg = items.groupby("order_id").agg(
        n_items=("order_item_id", "count"),
        n_sellers=("seller_id", "nunique"),
        n_products=("product_id", "nunique"),
        total_price=("price", "sum"),
        total_freight=("freight_value", "sum"),
        avg_price=("price", "mean"),
        avg_freight=("freight_value", "mean"),
        seller_id=("seller_id", "first"),
        product_weight_g=("product_weight_g", "sum"),
        product_photos_qty=("product_photos_qty", "mean"),
        category=("product_category_name_english", top_category),
    )
    return agg.reset_index()


def _aggregate_payments(payments: pd.DataFrame) -> pd.DataFrame:
    def top_payment(series: pd.Series) -> str:
        mode = series.dropna().mode()
        return mode.iloc[0] if len(mode) else "unknown"

    return (
        payments.groupby("order_id")
        .agg(
            n_payments=("payment_sequential", "count"),
            payment_value=("payment_value", "sum"),
            payment_installments=("payment_installments", "max"),
            payment_type=("payment_type", top_payment),
        )
        .reset_index()
    )


def build_late_delivery_dataset() -> pd.DataFrame:
    frames = _load_frames()
    orders = frames["orders"]

    # Label only for delivered orders with both dates present
    delivered = orders[
        (orders["order_status"] == "delivered")
        & orders["order_delivered_customer_date"].notna()
        & orders["order_estimated_delivery_date"].notna()
    ].copy()

    delivered["late"] = (
        delivered["order_delivered_customer_date"] > delivered["order_estimated_delivery_date"]
    ).astype(int)

    # Known at estimate time: promised window length
    delivered["estimated_days"] = (
        delivered["order_estimated_delivery_date"] - delivered["order_purchase_timestamp"]
    ).dt.total_seconds() / 86400

    delivered["purchase_hour"] = delivered["order_purchase_timestamp"].dt.hour
    delivered["purchase_dow"] = delivered["order_purchase_timestamp"].dt.dayofweek
    delivered["purchase_month"] = delivered["order_purchase_timestamp"].dt.month

    item_feats = _aggregate_items(frames["items"], frames["products"], frames["categories"])
    pay_feats = _aggregate_payments(frames["payments"])

    df = (
        delivered.merge(frames["customers"], on="customer_id", how="left")
        .merge(item_feats, on="order_id", how="left")
        .merge(pay_feats, on="order_id", how="left")
        .merge(frames["sellers"], on="seller_id", how="left")
    )

    df["same_state"] = (df["customer_state"] == df["seller_state"]).astype(int)
    df["category"] = df["category"].fillna("unknown")
    df["payment_type"] = df["payment_type"].fillna("unknown")

    # Seller past late-rate (time-aware): only prior orders of that seller
    df = df.sort_values("order_purchase_timestamp").reset_index(drop=True)
    df["seller_prior_orders"] = df.groupby("seller_id").cumcount()
    df["seller_prior_late_sum"] = df.groupby("seller_id")["late"].cumsum() - df["late"]
    # First order for a seller has no history -> 0.0 (avoid 0/0 and pd.NA cast issues)
    df["seller_prior_late_rate"] = np.where(
        df["seller_prior_orders"] > 0,
        df["seller_prior_late_sum"] / df["seller_prior_orders"],
        0.0,
    )

    feature_cols = [
        "order_id",
        "order_purchase_timestamp",
        "late",
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
        "customer_state",
        "seller_state",
        "category",
        "payment_type",
    ]
    out = df[feature_cols].dropna(subset=["n_items", "estimated_days"]).copy()
    return out


def save_late_delivery_dataset(path=None) -> pd.DataFrame:
    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    path = path or (PROCESSED_DIR / "late_delivery_orders.csv")
    df = build_late_delivery_dataset()
    df.to_csv(path, index=False)
    print(f"Saved {len(df):,} rows -> {path}")
    print(f"Late rate: {df['late'].mean():.2%}")
    return df


if __name__ == "__main__":
    save_late_delivery_dataset()
