import logging
import re

import httpx

from app.config import settings
from app.models.product import Product

logger = logging.getLogger(__name__)


def build_product_embedding_text(product: Product) -> str:
    """Combine product fields into a single string for embedding."""
    categories = ", ".join(product.categories)
    return f"{product.name}. {product.description}. Categories: {categories}"


def sanitize_search_query(query: str) -> str:
    """Light cleanup before sending text to external APIs."""
    cleaned = " ".join(query.split())
    if not re.search(r"[\w\u00C0-\u024F]", cleaned, re.UNICODE):
        raise ValueError("Query must contain meaningful text")
    return cleaned


async def embed_text(text: str) -> list[float] | None:
    """Embed text via Azure OpenAI; returns None when unavailable or on failure."""
    if not settings.azure_openai_enabled:
        return None

    url = (
        f"{settings.azure_openai_endpoint.rstrip('/')}"
        f"/openai/deployments/{settings.azure_openai_embedding_deployment}"
        f"/embeddings?api-version={settings.azure_openai_api_version}"
    )
    headers = {
        "api-key": settings.azure_openai_api_key,
        "Content-Type": "application/json",
    }
    payload = {"input": text}

    try:
        async with httpx.AsyncClient(timeout=settings.azure_openai_timeout_seconds) as client:
            response = await client.post(url, headers=headers, json=payload)
            response.raise_for_status()
            data = response.json()
            embedding = data["data"][0]["embedding"]
            if len(embedding) != settings.embedding_dimensions:
                logger.warning(
                    "Unexpected embedding size %s (expected %s)",
                    len(embedding),
                    settings.embedding_dimensions,
                )
            return embedding
    except Exception as exc:
        logger.warning("Azure embedding request failed: %s", exc)
        return None


async def refresh_product_embedding(product: Product) -> None:
    """Generate and persist embedding for a product when Azure is configured."""
    if not settings.azure_openai_enabled:
        return

    text = build_product_embedding_text(product)
    embedding = await embed_text(text)
    if embedding is None:
        return

    product.embedding = embedding
    await product.save()
