from functools import cached_property
from urllib.parse import quote_plus

from pydantic import Field, computed_field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    mongo_root_username: str = Field(min_length=1)
    mongo_root_password: str = Field(min_length=8)
    mongo_host: str = "localhost"
    mongo_port: int = 27017
    mongo_database: str = "ai_commerce"
    mongo_auth_source: str = "admin"
    # Optional full URI (Atlas mongodb+srv://...). Overrides host/port construction.
    mongodb_uri: str | None = None

    jwt_secret_key: str = Field(min_length=32)
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 15
    refresh_token_expire_days: int = 7

    # Cart pricing (Modül 1 §3.3)
    tax_rate: float = 0.20
    free_shipping_threshold: float = 500.0
    shipping_flat_rate: float = 29.99

    # Checkout & payment (Modül 1 §4)
    stock_reservation_minutes: int = 5
    checkout_session_minutes: int = 15
    mock_payment_failure_rate: float = 0.20

    # Smart search (Modül 2)
    # Embeddings: Azure OpenAI (project brief). Intent parsing can still use Gemini.
    # auto = Azure when configured, else Gemini.
    embedding_provider: str = "auto"
    embedding_dimensions: int = 768
    search_top_k: int = 5
    search_vector_index_name: str = "product_vector_index"

    azure_openai_endpoint: str | None = None
    azure_openai_api_key: str | None = None
    azure_openai_embedding_deployment: str = "text-embedding-3-small"
    azure_openai_api_version: str = "2024-10-21"
    azure_openai_timeout_seconds: float = 10.0

    gemini_api_key: str | None = None
    gemini_model: str = "gemini-1.5-flash"
    gemini_embedding_model: str = "gemini-embedding-001"
    gemini_api_version: str = "v1beta"
    gemini_timeout_seconds: float = 10.0

    @computed_field  # type: ignore[prop-decorator]
    @property
    def gemini_enabled(self) -> bool:
        return bool(self.gemini_api_key)

    @computed_field  # type: ignore[prop-decorator]
    @property
    def azure_openai_enabled(self) -> bool:
        return bool(
            self.azure_openai_endpoint
            and self.azure_openai_api_key
            and self.azure_openai_embedding_deployment
        )

    @computed_field  # type: ignore[prop-decorator]
    @property
    def active_embedding_provider(self) -> str | None:
        choice = (self.embedding_provider or "auto").strip().lower()
        if choice == "azure":
            return "azure" if self.azure_openai_enabled else None
        if choice == "gemini":
            return "gemini" if self.gemini_enabled else None
        if self.azure_openai_enabled:
            return "azure"
        if self.gemini_enabled:
            return "gemini"
        return None

    @computed_field  # type: ignore[prop-decorator]
    @property
    def embeddings_enabled(self) -> bool:
        return self.active_embedding_provider is not None

    @cached_property
    def mongodb_url(self) -> str:
        if self.mongodb_uri:
            return self.mongodb_uri
        username = quote_plus(self.mongo_root_username)
        password = quote_plus(self.mongo_root_password)
        return (
            f"mongodb://{username}:{password}@"
            f"{self.mongo_host}:{self.mongo_port}/{self.mongo_database}"
            f"?authSource={self.mongo_auth_source}"
        )


settings = Settings()
