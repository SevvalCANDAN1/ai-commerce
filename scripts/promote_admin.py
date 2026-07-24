"""Promote a registered user to store_admin by email."""

import asyncio
import sys

from beanie import init_beanie
from pymongo import AsyncMongoClient

from app.config import settings
from app.models.user import User, UserRole


async def promote_admin(email: str) -> None:
    client = AsyncMongoClient(settings.mongodb_url)
    db = client[settings.mongo_database]

    await init_beanie(database=db, document_models=[User])

    user = await User.find_one(User.email == email)
    if user is None:
        print(f"User not found: {email}")
        return

    user.role = UserRole.STORE_ADMIN
    await user.save()

    # Remove legacy field if it exists from older admin setup
    await db.users.update_one({"email": email}, {"$unset": {"is_superuser": ""}})

    print(f"Promoted to store_admin: {email}")
    print("Log in again to get a new JWT with role=store_admin.")


if __name__ == "__main__":
    target_email = sys.argv[1] if len(sys.argv) > 1 else "test@deneme.com"
    asyncio.run(promote_admin(target_email))
