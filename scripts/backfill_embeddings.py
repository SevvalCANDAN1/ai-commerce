"""Backfill product embeddings for existing catalog items."""

import asyncio
import sys

from beanie import init_beanie
from pymongo import AsyncMongoClient

from app.config import settings
from app.models.product import Product
from app.services.embedding_service import refresh_product_embedding


async def backfill() -> None:
    if not settings.gemini_enabled:
        print("Gemini is not configured. Set GEMINI_API_KEY.")
        sys.exit(1)

    client = AsyncMongoClient(settings.mongodb_url)
    await init_beanie(database=client[settings.mongo_database], document_models=[Product])

    products = await Product.find(Product.status != "deleted").to_list()
    updated = 0
    for product in products:
        await refresh_product_embedding(product)
        updated += 1
        print(f"Embedded: {product.name} ({product.id})")

    await client.close()
    print(f"Done. Processed {updated} products.")


if __name__ == "__main__":
    asyncio.run(backfill())
