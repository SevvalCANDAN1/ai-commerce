"""Azure OpenAI REST helpers (embeddings). Never log the API key."""

from urllib.parse import quote

from app.config import settings


def azure_openai_headers() -> dict[str, str]:
    return {
        "Content-Type": "application/json",
        "api-key": settings.azure_openai_api_key or "",
    }


def azure_embeddings_url() -> str:
    endpoint = (settings.azure_openai_endpoint or "").rstrip("/")
    deployment = quote(settings.azure_openai_embedding_deployment, safe="-_.")
    return (
        f"{endpoint}/openai/deployments/{deployment}/embeddings"
        f"?api-version={settings.azure_openai_api_version}"
    )
