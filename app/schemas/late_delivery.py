from typing import Literal

from pydantic import BaseModel, Field


class LateDeliveryRequest(BaseModel):
    """Features known around purchase time (same family as the Olist model)."""

    estimated_days: int = Field(default=7, ge=1, le=60)
    customer_state: str = Field(default="SP", min_length=1, max_length=32)
    seller_state: str = Field(default="SP", min_length=1, max_length=32)
    n_items: int = Field(default=1, ge=1, le=100)
    n_sellers: int = Field(default=1, ge=1, le=20)
    total_price: float = Field(..., gt=0)
    total_freight: float = Field(default=0, ge=0)
    category: str | None = None
    seller_prior_late_rate: float = Field(default=0.07, ge=0, le=1)
    payment_installments: int = Field(default=1, ge=1, le=24)


class LateDeliveryResponse(BaseModel):
    late: bool
    late_probability: float
    threshold: float
    risk: Literal["low", "medium", "high"]
    drivers: list[str]
    model: str
    order_id: str | None = None
    order_number: str | None = None
