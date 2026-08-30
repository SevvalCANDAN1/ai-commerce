import logging
import re

from beanie.operators import Or, RegEx

from app.config import settings
from app.core.storefront import is_storefront_visible
from app.database import get_mongo_client
from app.models.product import Product
from app.schemas.product import product_to_response
from app.schemas.search import ParsedSearchIntent, SearchResponse, SearchResultItem
from app.services.embedding_service import embed_text
from app.services.intent_service import parse_search_intent

logger = logging.getLogger(__name__)


def _cosine(a: list[float], b: list[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    na = sum(x * x for x in a) ** 0.5
    nb = sum(y * y for y in b) ** 0.5
    if na == 0 or nb == 0:
        return 0.0
    return dot / (na * nb)


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


async def _local_vector_scan(
    query_vector: list[float], top_k: int
) -> list[tuple[Product, float]]:
    """Cosine scan when Atlas $vectorSearch is unavailable (local mongo:7)."""
    products = await Product.find(
        Product.status == "published",
        Product.total_stock > 0,
        Product.embedding != None,  # noqa: E711
    ).to_list()
    scored = [
        (product, _cosine(query_vector, product.embedding or []))
        for product in products
        if is_storefront_visible(product)
    ]
    scored.sort(key=lambda item: item[1], reverse=True)
    return [(product, score) for product, score in scored[:top_k] if score > 0]


_COLOR_WORDS = {
    "mavi",
    "siyah",
    "beyaz",
    "kirmizi",
    "kırmızı",
    "yesil",
    "yeşil",
    "gri",
    "pembe",
    "turuncu",
}


def _content_keywords(intent: ParsedSearchIntent) -> list[str]:
    """Keywords that describe the product type, excluding color words."""
    return [
        word
        for word in intent.keywords
        if word.casefold() not in _COLOR_WORDS and len(word) >= 3
    ]


def _intent_has_filters(intent: ParsedSearchIntent) -> bool:
    return bool(
        intent.categories
        or intent.color
        or intent.size
        or _content_keywords(intent)
    )


def _product_text(product: Product) -> str:
    return f"{product.name} {product.description}".casefold()


def _matches_color(product: Product, wanted: str) -> bool:
    """
    Match variant.color only. A product with no colors is not excluded
    (mock termos often have color=null). A product whose colors are all
    different from `wanted` is excluded — even if the name contains that color.
    """
    named = [
        (variant.color or "").casefold()
        for variant in product.variants
        if variant.color
    ]
    if not named:
        return True
    return wanted.casefold() in named


def _matches_intent(product: Product, intent: ParsedSearchIntent) -> bool:
    """Apply structured intent as hybrid filters (Modül 2.3)."""
    content_words = _content_keywords(intent)
    if content_words:
        blob = _product_text(product)
        if not any(word.casefold() in blob for word in content_words):
            return False

    if intent.color and not _matches_color(product, intent.color):
        return False

    if intent.size:
        wanted = intent.size.casefold()
        if not any((variant.size or "").casefold() == wanted for variant in product.variants):
            return False

    return True


def _apply_intent_filters(
    hits: list[tuple[Product, float]],
    intent: ParsedSearchIntent,
    top_k: int,
) -> list[tuple[Product, float]]:
    if not _intent_has_filters(intent):
        return hits[:top_k]

    filtered = [(product, score) for product, score in hits if _matches_intent(product, intent)]
    if filtered:
        return filtered[:top_k]

    # Last resort: keep items that at least match product-type keywords.
    content_words = _content_keywords(intent)
    if content_words:
        keyword_hits = [
            (product, score)
            for product, score in hits
            if any(word.casefold() in _product_text(product) for word in content_words)
        ]
        if keyword_hits:
            return keyword_hits[:top_k]

    return hits[:top_k]


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
    Modül 2 pipeline:
    1. Parse free-text into structured intent (LLM proxy, with fallback).
    2. Embed the rewritten query (async; None on timeout → keyword fallback).
    3. Semantic match via Atlas $vectorSearch, else local cosine, Top-K.
       Visibility rules (published + stock) are pre-filters; intent filters
       (category / color / size) are applied on a wider candidate set.
    """
    limit = top_k or settings.search_top_k
    intent = await parse_search_intent(query)
    search_text = intent.rewritten_query or query
    fetch_k = limit * 5 if _intent_has_filters(intent) else limit

    query_vector = await embed_text(search_text, task_type="RETRIEVAL_QUERY")
    if query_vector is not None:
        semantic_hits: list[tuple[Product, float]] = []
        try:
            semantic_hits = await _vector_search(query_vector, fetch_k)
        except Exception as exc:
            logger.warning("Atlas vector search unavailable, using local cosine scan: %s", exc)

        if not semantic_hits:
            semantic_hits = await _local_vector_scan(query_vector, fetch_k)

        semantic_hits = _apply_intent_filters(semantic_hits, intent, limit)
        if semantic_hits:
            return SearchResponse(
                query=query,
                intent=intent,
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

    keyword_query = " ".join(intent.keywords) if intent.keywords else search_text
    keyword_fetch_k = limit * 5 if _intent_has_filters(intent) else limit
    keyword_hits = await _keyword_search(keyword_query, keyword_fetch_k)
    if _intent_has_filters(intent):
        filtered_keywords = [
            product for product in keyword_hits if _matches_intent(product, intent)
        ]
        keyword_hits = (filtered_keywords or keyword_hits)[:limit]
    else:
        keyword_hits = keyword_hits[:limit]
    return SearchResponse(
        query=query,
        intent=intent,
        mode="keyword",
        results=[
            SearchResultItem(product=product_to_response(product), score=None)
            for product in keyword_hits
        ],
        total=len(keyword_hits),
    )
