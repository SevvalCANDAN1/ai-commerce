from typing import Optional, List
from beanie import Document
from pydantic import BaseModel, EmailStr

class Address(BaseModel):
    """
    Embedded document for user addresses.
    Instead of a separate collection, we store addresses directly inside the User document.
    """
    title: str       # e.g., "Home", "Office"
    city: str
    country: str
    full_address: str
    zip_code: Optional[str] = None

class User(Document):
    email: EmailStr
    hashed_password: str
    full_name: Optional[str] = None
    is_active: bool = True
    is_superuser: bool = False
    
    # Embedded list of addresses
    addresses: List[Address] = []

    class Settings:
        name = "users"
