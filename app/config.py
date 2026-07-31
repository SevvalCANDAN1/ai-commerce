from functools import cached_property
from urllib.parse import quote_plus

from pydantic import Field
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

    jwt_secret_key: str = Field(min_length=32)
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 15
    refresh_token_expire_days: int = 7

    # Cart pricing (Modül 1 §3.3)
    tax_rate: float = 0.20
    free_shipping_threshold: float = 500.0
    shipping_flat_rate: float = 29.99

    @cached_property
    def mongodb_url(self) -> str:
        username = quote_plus(self.mongo_root_username)
        password = quote_plus(self.mongo_root_password)
        return (
            f"mongodb://{username}:{password}@"
            f"{self.mongo_host}:{self.mongo_port}/{self.mongo_database}"
            f"?authSource={self.mongo_auth_source}"
        )


settings = Settings()
