"""Backfill product embeddings for existing catalog items."""

import asyncio
import sys

from beanie import init_beanie
from pymongo import AsyncMongoClient

from app.config import settings
from app.models.product import Product
from app.services.embedding_service import refresh_product_embedding


async def backfill(force: bool = False) -> None:
    if not settings.gemini_enabled:
        print("Gemini is not configured. Set GEMINI_API_KEY.")
        sys.exit(1)

    client = AsyncMongoClient(settings.mongodb_url)
    await init_beanie(database=client[settings.mongo_database], document_models=[Product])

    products = await Product.find(Product.status != "deleted").to_list()

    # Clear stale embeddings that have the wrong dimension (e.g., after switching models).
    cleared = 0
    for product in products:
        embedding = product.embedding
        if embedding is not None and (force or len(embedding) != settings.embedding_dimensions):
            product.embedding = None
            await product.save()
            cleared += 1

    updated = 0
    for product in products:
        await refresh_product_embedding(product)
        if product.embedding is not None:
            updated += 1
            print(f"Embedded: {product.name} ({product.id})")

    await client.close()
    print(
        f"Done. Processed {len(products)} products, "
        f"cleared {cleared} stale embeddings, updated {updated}."
    )


if __name__ == "__main__":
    force = "--force" in sys.argv
    asyncio.run(backfill(force=force))
