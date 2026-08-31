import logging
import re

import httpx

from app.config import settings
from app.models.product import Product
from app.services.azure_openai_client import azure_embeddings_url, azure_openai_headers
from app.services.gemini_client import describe_http_error, gemini_headers, gemini_url

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


async def _embed_azure(text: str) -> list[float] | None:
    """Embed via Azure OpenAI text-embedding-3-* (dimensions kept at 768)."""
    payload = {
        "input": text,
        "dimensions": settings.embedding_dimensions,
    }
    try:
        async with httpx.AsyncClient(timeout=settings.azure_openai_timeout_seconds) as client:
            response = await client.post(
                azure_embeddings_url(),
                headers=azure_openai_headers(),
                json=payload,
            )
            response.raise_for_status()
            data = response.json()
            embedding = data["data"][0]["embedding"]
            if len(embedding) != settings.embedding_dimensions:
                logger.warning(
                    "Unexpected Azure embedding size %s (expected %s)",
                    len(embedding),
                    settings.embedding_dimensions,
                )
            return embedding
    except Exception as exc:
        logger.warning("Azure OpenAI embedding request failed: %s", describe_http_error(exc))
        return None


async def _embed_gemini(text: str, *, task_type: str) -> list[float] | None:
    url = gemini_url(settings.gemini_embedding_model, "embedContent")
    payload = {
        "model": f"models/{settings.gemini_embedding_model}",
        "content": {"parts": [{"text": text}]},
        "task_type": task_type,
        "output_dimensionality": settings.embedding_dimensions,
    }
    try:
        async with httpx.AsyncClient(timeout=settings.gemini_timeout_seconds) as client:
            response = await client.post(url, headers=gemini_headers(), json=payload)
            response.raise_for_status()
            data = response.json()
            embedding = data["embedding"]["values"]
            if len(embedding) != settings.embedding_dimensions:
                logger.warning(
                    "Unexpected Gemini embedding size %s (expected %s)",
                    len(embedding),
                    settings.embedding_dimensions,
                )
            return embedding
    except Exception as exc:
        logger.warning("Google embedding request failed: %s", describe_http_error(exc))
        return None


async def embed_text(
    text: str, *, task_type: str = "RETRIEVAL_DOCUMENT"
) -> list[float] | None:
    """Embed text via the active provider; returns None when unavailable or on failure."""
    provider = settings.active_embedding_provider
    if provider == "azure":
        return await _embed_azure(text)
    if provider == "gemini":
        return await _embed_gemini(text, task_type=task_type)
    return None


async def refresh_product_embedding(product: Product) -> None:
    """Generate and persist embedding for a product when an embedding provider is configured."""
    if not settings.embeddings_enabled:
        return

    text = build_product_embedding_text(product)
    embedding = await embed_text(text, task_type="RETRIEVAL_DOCUMENT")
    if embedding is None:
        return

    product.embedding = embedding
    await product.save()
