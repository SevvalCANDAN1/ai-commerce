from pydantic import BaseModel, EmailStr, Field
from typing import List

from app.models.user import Address

# Input schema for user registration
class UserRegisterRequest(BaseModel):
    email: EmailStr
    password: str = Field(..., min_length=6, description="Password must be at least 6 characters long")
    full_name: str | None = Field(default=None, description="Full name of the user")

# Output schema for user data (excluding sensitive data like password)
class UserResponse(BaseModel):
    id: str  # MongoDB ObjectId will be converted to string
    email: EmailStr
    full_name: str | None
    is_active: bool
    addresses: List[Address] = [] 

    class Config:
        from_attributes = True
