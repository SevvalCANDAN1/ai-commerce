from pymongo import AsyncMongoClient

from beanie import init_beanie

from app.config import settings

_mongo_client: AsyncMongoClient | None = None


async def connect_to_database(document_models: list) -> None:
    global _mongo_client
    _mongo_client = AsyncMongoClient(settings.mongodb_url)
    await init_beanie(
        database=_mongo_client[settings.mongo_database],
        document_models=document_models,
    )


async def close_database_connection() -> None:
    global _mongo_client
    if _mongo_client is not None:
        await _mongo_client.close()
        _mongo_client = None


def get_mongo_client() -> AsyncMongoClient:
    if _mongo_client is None:
        raise RuntimeError("MongoDB client is not initialized")
    return _mongo_client
