"""Create the MongoDB Atlas vector search index from atlas_vector_index.json."""

import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from pymongo import AsyncMongoClient

from app.config import settings
from app.models.product import Product


def _load_index_definition() -> dict:
    path = Path(__file__).with_name("atlas_vector_index.json")
    return json.loads(path.read_text(encoding="utf-8"))


async def create_vector_index() -> None:
    definition = _load_index_definition()

    client = AsyncMongoClient(settings.mongodb_url)
    db = client[settings.mongo_database]

    try:
        await db.command(
            "createSearchIndexes",
            Product.Settings.name,
            indexes=[
                {
                    "name": definition["name"],
                    "definition": definition["definition"],
                }
            ],
        )
        print(f"Vector search index '{definition['name']}' created.")
    except Exception as exc:
        print(f"Could not create vector search index: {exc}")
        print("Ensure you are connecting to MongoDB Atlas with Vector Search enabled.")
        print("Alternatively, create the index manually from scripts/atlas_vector_index.json.")
    finally:
        await client.close()


if __name__ == "__main__":
    asyncio.run(create_vector_index())
