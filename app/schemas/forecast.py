from pydantic import BaseModel, Field


class DemandPoint(BaseModel):
    week: str
    units: float | None = None
    predicted_units: float | None = None


class ForecastMetrics(BaseModel):
    source: str
    mae: float
    mape: float
    n_categories: int
    horizon_weeks: int
    trained_at: str


class CategoryForecastResponse(BaseModel):
    category: str
    product_id: str | None = None
    product_name: str | None = None
    metrics: ForecastMetrics
    history: list[DemandPoint]
    forecast: list[DemandPoint]


class CategoryListResponse(BaseModel):
    categories: list[str] = Field(default_factory=list)
    metrics: ForecastMetrics
