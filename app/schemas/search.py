import re
from typing import Literal

from pydantic import BaseModel, Field, field_validator

from app.schemas.product import ProductResponse


class SearchRequest(BaseModel):
    """Natural-language product search query with input validation."""

    query: str = Field(..., min_length=2, max_length=500)
    top_k: int | None = Field(default=None, ge=1, le=20)

    @field_validator("query")
    @classmethod
    def sanitize_query(cls, value: str) -> str:
        cleaned = " ".join(value.split())
        if not re.search(r"[\w\u00C0-\u024F]", cleaned, re.UNICODE):
            raise ValueError("Query must contain meaningful text")
        return cleaned


class SearchResultItem(BaseModel):
    product: ProductResponse
    score: float | None = None


class SearchResponse(BaseModel):
    query: str
    mode: Literal["semantic", "keyword"]
    results: list[SearchResultItem]
    total: int
