import logging

import httpx

from app.config import settings

logger = logging.getLogger(__name__)

_SYSTEM_PROMPT = (
    "You are an e-commerce search assistant. "
    "Rewrite the user's natural-language query into a short, "
    "search-engine-friendly keyword phrase. Preserve the original language. "
    "Return ONLY the rewritten phrase, with no extra explanation, quotes, or punctuation."
)


async def expand_search_query(query: str) -> str | None:
    """
    Expand a free-text search query into an embedding-friendly keyword phrase.

    Uses Google Gemini (free tier). Returns None when Gemini is not configured
    or the request fails, so the caller can fall back to the raw query.
    """
    if not settings.gemini_enabled:
        return None

    url = (
        f"https://generativelanguage.googleapis.com/"
        f"{settings.gemini_api_version}/models/{settings.gemini_model}:generateContent"
        f"?key={settings.gemini_api_key}"
    )
    headers = {"Content-Type": "application/json"}
    payload = {
        "contents": [
            {
                "role": "user",
                "parts": [
                    {"text": _SYSTEM_PROMPT},
                    {"text": f"User query: {query}"},
                ],
            }
        ],
        "generationConfig": {
            "temperature": 0.2,
            "maxOutputTokens": 128,
        },
    }

    try:
        async with httpx.AsyncClient(timeout=settings.gemini_timeout_seconds) as client:
            response = await client.post(url, headers=headers, json=payload)
            response.raise_for_status()
            data = response.json()

            candidate = data.get("candidates", [{}])[0]
            content = candidate.get("content", {})
            parts = content.get("parts", [])
            if not parts:
                return None

            expanded = parts[0].get("text", "").strip()
            if not expanded:
                return None

            logger.debug("Expanded query: %r -> %r", query, expanded)
            return expanded
    except Exception as exc:
        logger.warning("Gemini query expansion failed: %s", exc)
        return None
