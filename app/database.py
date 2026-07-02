from beanie import init_beanie
from pymongo import AsyncMongoClient

from app.config import settings


async def connect_to_database(document_models: list) -> None:
    client = AsyncMongoClient(settings.mongodb_url)
    await init_beanie(
        database=client[settings.mongo_database],
        document_models=document_models,
    )


async def close_database_connection() -> None:
    # AsyncMongoClient cleanup will be added when we manage the client instance globally.
    pass
