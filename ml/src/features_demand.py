"""Weekly category demand from Olist, or a synthetic series for local demos."""

from __future__ import annotations

import numpy as np
import pandas as pd

from ml.src.paths import PROCESSED_DIR, missing_raw_files, raw_path

SYNTHETIC_CATEGORIES = [
    "health_beauty",
    "bed_bath_table",
    "sports_leisure",
    "computers_accessories",
    "watches_gifts",
]


def _olist_weekly() -> pd.DataFrame:
    orders = pd.read_csv(
        raw_path("orders"),
        parse_dates=["order_purchase_timestamp"],
        usecols=["order_id", "order_purchase_timestamp", "order_status"],
    )
    items = pd.read_csv(
        raw_path("order_items"),
        usecols=["order_id", "product_id", "order_item_id", "price"],
    )
    products = pd.read_csv(
        raw_path("products"),
        usecols=["product_id", "product_category_name"],
    )
    categories = pd.read_csv(raw_path("category_translation"))

    orders = orders[orders["order_status"].isin(["delivered", "shipped", "invoiced"])]
    products = products.merge(categories, on="product_category_name", how="left")
    items = items.merge(products, on="product_id", how="left")
    items["category"] = items["product_category_name_english"].fillna("unknown")

    merged = items.merge(orders, on="order_id", how="inner")
    merged["week"] = (
        merged["order_purchase_timestamp"].dt.to_period("W-MON").dt.start_time
    )

    weekly = (
        merged.groupby(["category", "week"], as_index=False)
        .agg(units=("order_item_id", "count"), gmv=("price", "sum"))
    )
    return weekly


def _synthetic_weekly(n_weeks: int = 80, seed: int = 42) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    start = pd.Timestamp("2017-01-02")
    weeks = pd.date_range(start, periods=n_weeks, freq="7D")
    rows: list[dict] = []
    for i, category in enumerate(SYNTHETIC_CATEGORIES):
        base = 80 + i * 25
        for t, week in enumerate(weeks):
            seasonal = 18 * np.sin(2 * np.pi * t / 52)
            trend = 0.35 * t
            noise = rng.normal(0, 8)
            units = max(5, int(base + seasonal + trend + noise))
            rows.append(
                {
                    "category": category,
                    "week": week,
                    "units": units,
                    "gmv": float(units * (40 + i * 8)),
                }
            )
    return pd.DataFrame(rows)


def build_weekly_demand() -> tuple[pd.DataFrame, str]:
    if missing_raw_files():
        return _synthetic_weekly(), "synthetic"
    return _olist_weekly(), "olist"


def top_categories(weekly: pd.DataFrame, n: int = 15) -> pd.DataFrame:
    ranking = weekly.groupby("category")["units"].sum().sort_values(ascending=False)
    return weekly[weekly["category"].isin(ranking.head(n).index)].copy()


def save_weekly_demand() -> tuple[pd.DataFrame, str]:
    df, source = build_weekly_demand()
    if source == "olist":
        df = top_categories(df)
    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    path = PROCESSED_DIR / "weekly_category_demand.csv"
    df.to_csv(path, index=False)
    return df, source
