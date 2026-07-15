from datetime import datetime, timedelta, timezone
from jose import jwt
from passlib.context import CryptContext
from fastapi.security import OAuth2PasswordBearer
from fastapi import Depends, HTTPException, status
from jose import JWTError
from bson import ObjectId

from app.models.user import User
from app.config import settings


oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login")
# Password hashing context (bcrypt)
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verifies a plain password against the hashed password from the database."""
    return pwd_context.verify(plain_password, hashed_password)

def create_access_token(data: dict, expires_delta: timedelta | None = None) -> str:
    """Creates a JSON Web Token (JWT) with encoded user data and expiration."""
    # Copy data to avoid mutating the original dictionary
    to_encode = data.copy()
    
    # Set expiration time (default to 30 minutes if not provided)
    if expires_delta:
        expire = datetime.now(timezone.utc) + expires_delta
    else:
        expire = datetime.now(timezone.utc) + timedelta(minutes=30)
        
    # Standard JWT 'exp' claim
    to_encode.update({"exp": expire})
    
    # Encode and sign the JWT using the secret key from settings
    encoded_jwt = jwt.encode(
        to_encode, 
        settings.jwt_secret_key, 
        algorithm=settings.jwt_algorithm
    )
    
    return encoded_jwt

async def get_current_user(token: str = Depends(oauth2_scheme)) -> User:
    """
    Validates the JWT token, extracts the user ID, and fetches the user from the database.
    Acts as the primary dependency for protected routes.
    """
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    
    try:
        # 1. Decode the token using the secret key
        payload = jwt.decode(
            token, 
            settings.jwt_secret_key, 
            algorithms=[settings.jwt_algorithm]
        )
        
        # 2. Extract user ID (subject claim)
        user_id: str = payload.get("sub")
        if user_id is None:
            raise credentials_exception
    except JWTError:
        raise credentials_exception
    # 3. Retrieve user from database
    user = await User.get(ObjectId(user_id))
    
    if user is None:
        raise credentials_exception
        
    return user
async def get_current_superuser(current_user: User = Depends(get_current_user)) -> User:
    """
    Validates if the current authenticated user has superuser (admin) privileges.
    """
    if not current_user.is_superuser:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You don't have enough privileges"
        )
    return current_user
