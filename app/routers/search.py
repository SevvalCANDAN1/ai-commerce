from fastapi import APIRouter, Query

from app.schemas.search import SearchRequest, SearchResponse
from app.services.search_service import smart_search

router = APIRouter(
    prefix="/search",
    tags=["Smart Search"],
)


@router.post("/", response_model=SearchResponse)
async def search_products(request: SearchRequest):
    """
    Natural-language product search (Modül 2).

    Accepts free-text queries like "hafta sonu kamp için sıcak tutacak ekipman".
    Parses intent via Gemini, embeds the rewritten query, then scores with
    MongoDB Atlas Vector Search (or local cosine). Falls back to keyword search.
    """
    return await smart_search(query=request.query, top_k=request.top_k)


@router.get("/", response_model=SearchResponse)
async def search_products_get(
    q: str = Query(..., min_length=2, max_length=500),
    top_k: int | None = Query(default=None, ge=1, le=20),
):
    """GET variant for quick testing; same logic as POST /search."""
    request = SearchRequest(query=q, top_k=top_k)
    return await smart_search(query=request.query, top_k=request.top_k)
