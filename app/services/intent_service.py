import json
import logging
import re

import httpx

from app.config import settings
from app.schemas.search import ParsedSearchIntent
from app.services.gemini_client import describe_http_error, gemini_headers, gemini_url

logger = logging.getLogger(__name__)

# Catalog values the LLM is allowed to emit as filters.
_ALLOWED_CATEGORIES = {
    "electronics",
    "computers_accessories",
    "health_beauty",
    "sports_leisure",
    "bed_bath_table",
    "furniture_decor",
    "watches_gifts",
    "office",
    "stationery",
    "giyim",
    "erkek",
    "kadin",
    "tisort",
}

_COLOR_ALIASES = {
    "mavi": "Mavi",
    "siyah": "Siyah",
    "beyaz": "Beyaz",
    "kirmizi": "Kirmizi",
    "kırmızı": "Kirmizi",
    "yesil": "Yesil",
    "yeşil": "Yesil",
    "gri": "Gri",
    "pembe": "Pembe",
    "turuncu": "Turuncu",
}

_CATEGORY_HINTS = {
    "kamp": "sports_leisure",
    "termos": "sports_leisure",
    "cadir": "sports_leisure",
    "çadır": "sports_leisure",
    "yoga": "sports_leisure",
    "klavye": "computers_accessories",
    "mouse": "computers_accessories",
    "laptop": "computers_accessories",
    "kulaklik": "electronics",
    "kulaklık": "electronics",
    "saat": "watches_gifts",
    "kalem": "stationery",
    "tisort": "tisort",
    "tişört": "tisort",
}

_STOPWORDS = {
    "icin",
    "için",
    "ile",
    "bir",
    "ve",
    "hafta",
    "sonu",
    "uygun",
    "gibi",
    "olan",
    "the",
    "for",
    "and",
}


def local_intent(query: str) -> ParsedSearchIntent:
    """Rule-based intent when Gemini is unavailable (401, timeout, no key)."""
    tokens = re.findall(r"[A-Za-zÇĞİÖŞÜçğıöşü0-9]+", query.lower())
    color: str | None = None
    keywords: list[str] = []
    categories: list[str] = []

    for token in tokens:
        if token in _COLOR_ALIASES:
            color = _COLOR_ALIASES[token]
        if token in _CATEGORY_HINTS:
            category = _CATEGORY_HINTS[token]
            if category not in categories:
                categories.append(category)
        if token not in _STOPWORDS and len(token) >= 3:
            keywords.append(token)

    rewritten = " ".join(keywords) or query
    return ParsedSearchIntent(
        rewritten_query=rewritten,
        intent="product_search",
        keywords=keywords,
        categories=categories,
        color=color,
        size=None,
    )


_SYSTEM_PROMPT = (
    "You are an e-commerce search intent parser. "
    "Read the user's natural-language query (Turkish or English) and return "
    "ONLY valid JSON with this shape:\n"
    "{\n"
    '  "rewritten_query": "short keyword phrase for product search, same language",\n'
    '  "intent": "product_search",\n'
    '  "keywords": ["kamp", "termos"],\n'
    '  "categories": ["sports_leisure"],\n'
    '  "color": "Mavi",\n'
    '  "size": "M"\n'
    "}\n"
    "Allowed categories: "
    + ", ".join(sorted(_ALLOWED_CATEGORIES))
    + ". "
    "Use null for color/size when unknown. Use [] for unknown lists. "
    "Do not invent filters the user did not imply."
)


def fallback_intent(query: str) -> ParsedSearchIntent:
    """Safe default when Gemini is off or the response cannot be parsed."""
    return local_intent(query)


def _extract_json_object(text: str) -> dict | None:
    cleaned = text.strip()
    fenced = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", cleaned, re.DOTALL)
    if fenced:
        cleaned = fenced.group(1)
    else:
        start = cleaned.find("{")
        end = cleaned.rfind("}")
        if start == -1 or end == -1:
            return None
        cleaned = cleaned[start : end + 1]

    try:
        data = json.loads(cleaned)
    except json.JSONDecodeError:
        return None
    return data if isinstance(data, dict) else None


def _normalize_intent(query: str, data: dict) -> ParsedSearchIntent:
    rewritten = str(data.get("rewritten_query") or query).strip() or query
    intent_name = str(data.get("intent") or "product_search").strip() or "product_search"

    keywords = [
        str(word).strip()
        for word in data.get("keywords") or []
        if str(word).strip()
    ]

    categories = []
    for category in data.get("categories") or []:
        normalized = str(category).strip().lower()
        if normalized in _ALLOWED_CATEGORIES:
            categories.append(normalized)

    color = data.get("color")
    color = str(color).strip() if color else None
    size = data.get("size")
    size = str(size).strip() if size else None

    return ParsedSearchIntent(
        rewritten_query=rewritten,
        intent=intent_name,
        keywords=keywords,
        categories=categories,
        color=color or None,
        size=size or None,
    )


async def parse_search_intent(query: str) -> ParsedSearchIntent:
    """
    Thin Gemini proxy: clean text in, structured intent out.

    On any failure we return fallback_intent so search never depends on the LLM.
    """
    if not settings.gemini_enabled:
        return fallback_intent(query)

    url = gemini_url(settings.gemini_model, "generateContent")
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
            "temperature": 0.1,
            "maxOutputTokens": 256,
            "responseMimeType": "application/json",
        },
    }

    try:
        async with httpx.AsyncClient(timeout=settings.gemini_timeout_seconds) as client:
            response = await client.post(url, headers=gemini_headers(), json=payload)
            response.raise_for_status()
            data = response.json()

            candidate = data.get("candidates", [{}])[0]
            parts = candidate.get("content", {}).get("parts", [])
            raw_text = parts[0].get("text", "") if parts else ""
            parsed = _extract_json_object(raw_text)
            if not parsed:
                logger.warning("Gemini intent response was not valid JSON")
                return fallback_intent(query)

            intent = _normalize_intent(query, parsed)
            logger.debug("Parsed search intent: %s", intent.model_dump())
            return intent
    except Exception as exc:
        logger.warning("Gemini intent parsing failed: %s", describe_http_error(exc))
        return fallback_intent(query)
