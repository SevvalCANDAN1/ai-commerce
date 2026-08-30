"""Shared Gemini HTTP helpers (Modül 2)."""

from app.config import settings


def gemini_headers() -> dict[str, str]:
    """
    Auth keys from AI Studio (prefix AQ.) must be sent as x-goog-api-key.
    Query-string ?key= is the old AIza traffic-key style and returns 401.
    """
    return {
        "Content-Type": "application/json",
        "x-goog-api-key": settings.gemini_api_key or "",
    }


def gemini_url(model: str, method: str) -> str:
    return (
        f"https://generativelanguage.googleapis.com/"
        f"{settings.gemini_api_version}/models/{model}:{method}"
    )


def describe_http_error(exc: Exception) -> str:
    """Log-safe error text: status + short body, never the API key."""
    response = getattr(exc, "response", None)
    if response is not None:
        body = (response.text or "")[:200].replace("\n", " ")
        return f"{response.status_code} {body}"
    return str(exc)
