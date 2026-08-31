"""Seed a larger mock catalog for demos and load testing."""

import asyncio
import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from beanie import init_beanie
from pymongo import AsyncMongoClient

from app.config import settings
from app.models.product import Product, Variant
from app.schemas.product import calculate_total_stock
from app.services.embedding_service import refresh_product_embedding

CATEGORIES = [
    "electronics",
    "computers_accessories",
    "health_beauty",
    "sports_leisure",
    "bed_bath_table",
    "furniture_decor",
    "watches_gifts",
    "office",
    "stationery",
    "giyim",
    "erkek",
    "kadin",
    "tisort",
]

COLORS = ["Siyah", "Beyaz", "Mavi", "Kirmizi", "Yesil", "Gri", "Pembe", "Turuncu"]
SIZES = ["XS", "S", "M", "L", "XL", "XXL", "Standard", "Mini", "Büyük"]

MOCK_PRODUCT_TEMPLATES = [
    ("Kablosuz Mouse", "Ergonomik tasarımlı kablosuz bilgisayar mouse'u.", "computers_accessories"),
    ("Mekanik Klavye", "RGB aydınlatmalı mekanik oyuncu klavyesi.", "computers_accessories"),
    ("Laptop Standı", "Alüminyum, ayarlanabilir yükseklikte laptop standı.", "computers_accessories"),
    ("USB-C Hub", "7'si 1 arada USB-C çoklayıcı ve adaptör.", "computers_accessories"),
    ("Monitör Lambası", "Göz yormayan ekran üstü LED lamba.", "electronics"),
    ("Bluetooth Kulaklık", "Gürültü önleyicili kablosuz kulaklık.", "electronics"),
    ("Akıllı Saat", "Adım sayar, nabız ölçer ve uyku takibi.", "watches_gifts"),
    ("Yüz Temizleme Cihazı", "Cilt bakımı için sonik temizleme cihazı.", "health_beauty"),
    ("Organik Şampuan", "Doğal içerikli, sülfatsız şampuan.", "health_beauty"),
    ("Kamp Çadırı", "2 kişilik, hafif ve su geçirmez kamp çadırı.", "sports_leisure"),
    ("Yoga Matı", "Kaymaz, 6mm kalınlıkta yoga matı.", "sports_leisure"),
    ("Termos", "500ml paslanmaz çelik termos.", "sports_leisure"),
    ("Pamuklu Nevresim Takımı", "Çift kişilik yumuşak pamuklu nevresim.", "bed_bath_table"),
    ("Yastık Kılıfı", "2'li set, anti-alerjik yastık kılıfı.", "bed_bath_table"),
    ("Masa Lambası", "Modern tasarımlı, dokunmatik dimmerli masa lambası.", "furniture_decor"),
    ("Duvar Rafı", "3'lü ahşap duvar rafı seti.", "furniture_decor"),
    ("Mavi Tükenmez Kalem", "Ofis ve okul kullanımına uygun mavi kalem.", "stationery"),
    ("A4 Fotokopi Kağıdı", "500'lü paket, 80 gr A4 fotokopi kağıdı.", "office"),
    ("Not Defteri", "Çizgili, 120 sayfa, sert kapaklı not defteri.", "stationery"),
    ("Spor Tişört", "Nefes alabilen, ter tutmayan spor tişört.", "giyim"),
    ("Kot Pantolon", "Klasik kesim, rahat kullanımlı kot pantolon.", "giyim"),
    ("Kadın Eşarp", "İpek dokulu, şık kadın eşarp.", "kadin"),
    ("Erkek Ceket", "Günlük kullanıma uygun, hafif erkek ceket.", "erkek"),
]


def _build_variants(index: int, base_price: float) -> list[Variant]:
    """Generate 1-3 variants with random color/size/stock and occasional price override."""
    variant_count = random.randint(1, 3)
    variants: list[Variant] = []
    used_skus: set[str] = set()

    for v in range(variant_count):
        sku = f"MOCK-{index:04d}-{v + 1}"
        used_skus.add(sku)
        color = random.choice(COLORS) if random.random() > 0.3 else None
        size = random.choice(SIZES) if random.random() > 0.3 else None
        stock = random.randint(5, 200)
        price_override = round(base_price * random.uniform(0.85, 1.25), 2) if random.random() > 0.6 else None

        variants.append(
            Variant(
                sku=sku,
                color=color,
                size=size,
                stock=stock,
                price_override=price_override,
            )
        )

    return variants


async def seed(count: int = 50, with_embeddings: bool = True) -> None:
    client = AsyncMongoClient(settings.mongodb_url)
    await init_beanie(database=client[settings.mongo_database], document_models=[Product])

    created = 0
    skipped = 0

    for i in range(count):
        template = random.choice(MOCK_PRODUCT_TEMPLATES)
        name, description, primary_category = template
        name = f"{name} #{i + 1}"

        base_price = round(random.uniform(10.0, 500.0), 2)
        variants = _build_variants(i + 1, base_price)

        # Add 0-2 extra categories for richer search/forecast demo data
        extra_categories = random.sample(CATEGORIES, k=random.randint(0, 2))
        categories = list({primary_category, *extra_categories})

        existing = await Product.find_one(Product.name == name)
        if existing:
            skipped += 1
            continue

        product = Product(
            name=name,
            description=description,
            base_price=base_price,
            categories=categories,
            variants=variants,
            status="published",
            total_stock=calculate_total_stock(variants),
        )
        await product.insert()

        if with_embeddings and settings.embeddings_enabled:
            await refresh_product_embedding(product)

        created += 1
        if created % 10 == 0:
            print(f"Seeded {created} products...")

    await client.close()
    print(f"Done. Created {created} products, skipped {skipped} (already existed).")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Seed mock products into the catalog.")
    parser.add_argument("--count", type=int, default=50, help="Number of products to create")
    parser.add_argument(
        "--no-embeddings",
        action="store_true",
        help="Skip generating embeddings even if an embedding provider is configured",
    )
    args = parser.parse_args()

    asyncio.run(seed(count=args.count, with_embeddings=not args.no_embeddings))
