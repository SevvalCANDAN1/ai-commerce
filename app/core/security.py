import hashlib
import secrets
from datetime import datetime, timedelta, timezone

from bson import ObjectId
from bson.errors import InvalidId
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
from passlib.context import CryptContext

from app.config import settings
from app.models.refresh_token import RefreshToken
from app.models.user import User, UserRole

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login")
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def hash_password(plain_password: str) -> str:
    """Hashes a plain text password for storage."""
    return pwd_context.hash(plain_password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verifies a plain password against the hashed password from the database."""
    return pwd_context.verify(plain_password, hashed_password)


def _hash_refresh_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


async def create_refresh_token(user: User) -> str:
    """Creates a refresh token, stores its hash, and returns the plain token once."""
    plain_token = secrets.token_urlsafe(32)
    expires_at = datetime.now(timezone.utc) + timedelta(days=settings.refresh_token_expire_days)

    await RefreshToken(
        user_id=user.id,
        token_hash=_hash_refresh_token(plain_token),
        expires_at=expires_at,
    ).insert()

    return plain_token


async def revoke_refresh_token(refresh_token: str) -> None:
    """Marks a refresh token as revoked if it exists."""
    stored_token = await RefreshToken.find_one(
        RefreshToken.token_hash == _hash_refresh_token(refresh_token)
    )
    if stored_token is None:
        return

    stored_token.revoked = True
    await stored_token.save()


async def validate_refresh_token(refresh_token: str) -> User:
    """Validates a refresh token and returns the associated active user."""
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid or expired refresh token",
        headers={"WWW-Authenticate": "Bearer"},
    )

    stored_token = await RefreshToken.find_one(
        RefreshToken.token_hash == _hash_refresh_token(refresh_token),
        RefreshToken.revoked == False,
    )
    if stored_token is None:
        raise credentials_exception

    if stored_token.expires_at <= datetime.now(timezone.utc):
        stored_token.revoked = True
        await stored_token.save()
        raise credentials_exception

    user = await User.get(stored_token.user_id)
    if user is None or not user.is_active:
        raise credentials_exception

    return user


async def issue_token_pair(user: User) -> tuple[str, str]:
    """Issues a short-lived access token and a long-lived refresh token."""
    access_token = create_access_token(
        data={
            "sub": str(user.id),
            "role": user.role.value,
        },
        expires_delta=timedelta(minutes=settings.access_token_expire_minutes),
    )
    refresh_token = await create_refresh_token(user)
    return access_token, refresh_token


def create_access_token(data: dict, expires_delta: timedelta | None = None) -> str:
    """Creates a JSON Web Token (JWT) with encoded user data and expiration."""
    to_encode = data.copy()

    if expires_delta:
        expire = datetime.now(timezone.utc) + expires_delta
    else:
        expire = datetime.now(timezone.utc) + timedelta(
            minutes=settings.access_token_expire_minutes
        )

    to_encode.update({"exp": expire})

    return jwt.encode(
        to_encode,
        settings.jwt_secret_key,
        algorithm=settings.jwt_algorithm,
    )


async def get_token_payload(token: str = Depends(oauth2_scheme)) -> dict:
    """Decodes and returns the JWT payload after signature verification."""
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )

    try:
        return jwt.decode(
            token,
            settings.jwt_secret_key,
            algorithms=[settings.jwt_algorithm],
        )
    except JWTError:
        raise credentials_exception


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
        payload = jwt.decode(
            token,
            settings.jwt_secret_key,
            algorithms=[settings.jwt_algorithm],
        )
        user_id: str | None = payload.get("sub")
        if user_id is None:
            raise credentials_exception
        object_id = ObjectId(user_id)
    except (JWTError, InvalidId):
        raise credentials_exception

    user = await User.get(object_id)

    if user is None or not user.is_active:
        raise credentials_exception

    return user


async def get_current_store_admin(current_user: User = Depends(get_current_user)) -> User:
    """Requires an authenticated user with store_admin role (DB is source of truth)."""
    if current_user.role != UserRole.STORE_ADMIN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You don't have enough privileges",
        )
    return current_user


def require_role(*allowed_roles: UserRole):
    """Fast dependency factory that checks role from the JWT without a DB round-trip."""

    async def role_checker(payload: dict = Depends(get_token_payload)) -> dict:
        token_role = payload.get("role")
        allowed_values = {role.value for role in allowed_roles}
        if token_role not in allowed_values:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You don't have enough privileges",
            )
        return payload

    return role_checker
