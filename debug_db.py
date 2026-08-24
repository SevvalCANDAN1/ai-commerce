import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from beanie import init_beanie
from motor.motor_asyncio import AsyncIOMotorClient
from app.config import settings
from app.models.product import Product

async def main():
    client = AsyncIOMotorClient(settings.mongodb_url)
    db = client[settings.mongo_database]
    await init_beanie(database=db, document_models=[Product])
    
    products = await Product.find(
        Product.status == "published",
        Product.total_stock > 0
    ).to_list()
    
    print("=== BEANIE QUERY RESULTS ===")
    for p in products:
        print(p)
    print("============================")

if __name__ == "__main__":
    asyncio.run(main())
