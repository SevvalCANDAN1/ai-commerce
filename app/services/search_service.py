import logging
import re

from beanie.operators import Or, RegEx

from app.config import settings
from app.core.storefront import is_storefront_visible
from app.database import get_mongo_client
from app.models.product import Product
from app.schemas.product import product_to_response
from app.schemas.search import SearchResponse, SearchResultItem
from app.services.embedding_service import embed_text

logger = logging.getLogger(__name__)


async def _vector_search(query_vector: list[float], top_k: int) -> list[tuple[Product, float]]:
    client = get_mongo_client()
    collection = client[settings.mongo_database][Product.Settings.name]

    pipeline = [
        {
            "$vectorSearch": {
                "index": settings.search_vector_index_name,
                "path": "embedding",
                "queryVector": query_vector,
                "numCandidates": max(top_k * 20, 100),
                "limit": top_k,
                "filter": {
                    "status": "published",
                    "total_stock": {"$gt": 0},
                },
            }
        },
        {
            "$addFields": {
                "score": {"$meta": "vectorSearchScore"},
            }
        },
    ]

    cursor = await collection.aggregate(pipeline)
    docs = await cursor.to_list(length=top_k)

    results: list[tuple[Product, float]] = []
    for doc in docs:
        product = await Product.get(doc["_id"])
        if product is None or not is_storefront_visible(product):
            continue
        results.append((product, float(doc.get("score", 0.0))))
    return results


async def _keyword_search(query: str, top_k: int) -> list[Product]:
    """Traditional keyword search used as fallback when embeddings/vector search fail."""
    words = [word for word in re.split(r"\s+", query.strip()) if len(word) >= 2]
    if not words:
        words = [query.strip()]

    pattern_conditions = []
    for word in words:
        pattern_conditions.extend(
            [
                RegEx(Product.name, word, "i"),
                RegEx(Product.description, word, "i"),
                RegEx(Product.categories, word, "i"),
            ]
        )

    products = await Product.find(
        Product.status == "published",
        Product.total_stock > 0,
        Or(*pattern_conditions),
    ).limit(top_k).to_list()

    return products


async def smart_search(query: str, top_k: int | None = None) -> SearchResponse:
    """
    Semantic search via MongoDB Atlas Vector Search with keyword fallback.
    Pre-filters published products with stock (Modül 1 visibility rules).
    """
    limit = top_k or settings.search_top_k

    query_vector = await embed_text(query)
    if query_vector is not None:
        try:
            semantic_hits = await _vector_search(query_vector, limit)
            if semantic_hits:
                return SearchResponse(
                    query=query,
                    mode="semantic",
                    results=[
                        SearchResultItem(
                            product=product_to_response(product),
                            score=score,
                        )
                        for product, score in semantic_hits
                    ],
                    total=len(semantic_hits),
                )
        except Exception as exc:
            logger.warning("Vector search unavailable, using keyword fallback: %s", exc)

    keyword_hits = await _keyword_search(query, limit)
    return SearchResponse(
        query=query,
        mode="keyword",
        results=[
            SearchResultItem(product=product_to_response(product), score=None)
            for product in keyword_hits
        ],
        total=len(keyword_hits),
    )
