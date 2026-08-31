from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.core.security import get_current_store_admin
from app.models.user import User
from app.routers.product import get_product_or_404
from app.schemas.forecast import CategoryForecastResponse, CategoryListResponse
from app.schemas.late_delivery import LateDeliveryRequest, LateDeliveryResponse
from app.services.forecast_service import (
    category_forecast,
    forecast_ready,
    list_categories,
    load_forecast_artifact,
    product_forecast,
)
from app.services.late_delivery_service import score_features, score_order

router = APIRouter(
    prefix="/forecast",
    tags=["Demand Forecast"],
    dependencies=[Depends(get_current_store_admin)],
)


def _ensure_model() -> None:
    if not forecast_ready():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Demand model is not trained. Run: python -m ml.src.train_demand",
        )


@router.get("/categories", response_model=CategoryListResponse)
async def get_forecast_categories(_admin: User = Depends(get_current_store_admin)):
    """List categories the demand model can forecast (B2B)."""
    _ensure_model()
    artifact = load_forecast_artifact()
    return CategoryListResponse(categories=list_categories(), metrics=artifact["metrics"])


@router.get("/categories/{category}", response_model=CategoryForecastResponse)
async def get_category_forecast(
    category: str,
    weeks: int = Query(default=4, ge=1, le=8),
    _admin: User = Depends(get_current_store_admin),
):
    """Weekly unit demand forecast for a product category."""
    _ensure_model()
    try:
        return category_forecast(category, weeks)
    except KeyError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No forecast for category '{category}'. See GET /forecast/categories.",
        )


@router.get("/products/{product_id}", response_model=CategoryForecastResponse)
async def get_product_forecast(
    product_id: str,
    weeks: int = Query(default=4, ge=1, le=8),
    _admin: User = Depends(get_current_store_admin),
):
    """Forecast using the product's first catalog category."""
    _ensure_model()
    product = await get_product_or_404(product_id)
    try:
        return product_forecast(product, weeks)
    except KeyError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Product category is not in the demand model.",
        )


@router.post("/late-delivery", response_model=LateDeliveryResponse)
async def predict_late_delivery(
    request: LateDeliveryRequest,
    _admin: User = Depends(get_current_store_admin),
):
    """Purchase-time late-delivery risk (B2B). Uses Olist-style features."""
    return score_features(request)


@router.post("/late-delivery/orders/{order_id}", response_model=LateDeliveryResponse)
async def predict_late_delivery_for_order(
    order_id: str,
    estimated_days: int = Query(default=7, ge=1, le=60),
    _admin: User = Depends(get_current_store_admin),
):
    """Score an existing store order by mapping its snapshot onto the same features."""
    try:
        return await score_order(order_id, estimated_days=estimated_days)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Order not found",
        )
