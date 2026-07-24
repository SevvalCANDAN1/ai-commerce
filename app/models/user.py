from enum import StrEnum
from typing import List, Optional

from beanie import Document
from pydantic import BaseModel, EmailStr


class UserRole(StrEnum):
    CUSTOMER = "customer"
    STORE_ADMIN = "store_admin"


class Address(BaseModel):
    """Embedded document for user addresses."""

    title: str
    city: str
    country: str
    full_address: str
    zip_code: Optional[str] = None


class User(Document):
    email: EmailStr
    hashed_password: str
    full_name: Optional[str] = None
    role: UserRole = UserRole.CUSTOMER
    is_active: bool = True
    addresses: List[Address] = []

    class Settings:
        name = "users"
