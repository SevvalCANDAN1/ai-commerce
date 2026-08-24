"""Seed a small published catalog for search + forecast demos."""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from beanie import init_beanie
from pymongo import AsyncMongoClient

from app.config import settings
from app.models.product import Product, Variant
from app.schemas.product import calculate_total_stock
from app.services.embedding_service import refresh_product_embedding

DEMO_PRODUCTS = [
    {
        "name": "Kamp uyku tulumu",
        "description": "Hafta sonu kampı için üç mevsim, sıcak tutan hafif uyku tulumu.",
        "base_price": 1299.0,
        "categories": ["sports_leisure"],
    },
    {
        "name": "Termal polar mont",
        "description": "Soğuk hava ve açık hava aktiviteleri için nefes alabilen polar mont.",
        "base_price": 1890.0,
        "categories": ["sports_leisure"],
    },
    {
        "name": "Cilt bakım seti",
        "description": "Günlük nemlendirici ve temizlik ürünleri içeren sağlık ve güzellik seti.",
        "base_price": 449.0,
        "categories": ["health_beauty"],
    },
    {
        "name": "Pamuklu nevresim takımı",
        "description": "Yatak odası için çift kişilik yumuşak pamuklu nevresim.",
        "base_price": 799.0,
        "categories": ["bed_bath_table"],
    },
    {
        "name": "Kablosuz mouse",
        "description": "Ofis ve ev kullanımı için sessiz tıklamalı bilgisayar aksesuarı.",
        "base_price": 329.0,
        "categories": ["computers_accessories"],
    },
    {
        "name": "Minimal kol saati",
        "description": "Hediye için uygun, paslanmaz çelik kasa klasik kol saati.",
        "base_price": 2150.0,
        "categories": ["watches_gifts"],
    },
]


async def seed() -> None:
    client = AsyncMongoClient(settings.mongodb_url)
    await init_beanie(database=client[settings.mongo_database], document_models=[Product])

    created = 0
    for item in DEMO_PRODUCTS:
        existing = await Product.find_one(Product.name == item["name"])
        if existing:
            print(f"Skip (exists): {item['name']}")
            continue
        variants = [Variant(sku=f"DEMO-{created + 1:03d}", stock=25)]
        product = Product(
            name=item["name"],
            description=item["description"],
            base_price=item["base_price"],
            categories=item["categories"],
            variants=variants,
            status="published",
            total_stock=calculate_total_stock(variants),
        )
        await product.insert()
        await refresh_product_embedding(product)
        created += 1
        print(f"Seeded: {product.name}")

    await client.close()
    print(f"Done. Created {created} products.")


if __name__ == "__main__":
    asyncio.run(seed())
