import json
import re
from functools import lru_cache
from pathlib import Path

from app.models.product import Product

_ARTIFACT = Path(__file__).resolve().parents[2] / "ml" / "models" / "demand_forecast.json"


def _slug(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", value.strip().lower()).strip("_")


@lru_cache(maxsize=1)
def load_forecast_artifact() -> dict:
    if not _ARTIFACT.exists():
        raise FileNotFoundError(
            "Demand model is not trained. Run: python -m ml.src.train_demand"
        )
    return json.loads(_ARTIFACT.read_text(encoding="utf-8"))


def forecast_ready() -> bool:
    return _ARTIFACT.exists()


def list_categories() -> list[str]:
    artifact = load_forecast_artifact()
    return sorted(artifact["categories"].keys())


def resolve_category(name: str) -> str | None:
    artifact = load_forecast_artifact()
    categories = artifact["categories"]
    if name in categories:
        return name
    slug = _slug(name)
    if slug in categories:
        return slug
    for category in categories:
        if _slug(category) == slug or slug in _slug(category):
            return category
    return None


def category_forecast(category: str, weeks: int) -> dict:
    artifact = load_forecast_artifact()
    resolved = resolve_category(category)
    if resolved is None:
        raise KeyError(category)
    payload = artifact["categories"][resolved]
    horizon = max(1, min(weeks, len(payload["forecast"])))
    return {
        "category": resolved,
        "metrics": artifact["metrics"],
        "history": payload["history"],
        "forecast": payload["forecast"][:horizon],
    }


def product_forecast(product: Product, weeks: int) -> dict:
    if not product.categories:
        raise KeyError("product has no categories")
    result = category_forecast(product.categories[0], weeks)
    result["product_id"] = str(product.id)
    result["product_name"] = product.name
    return result
