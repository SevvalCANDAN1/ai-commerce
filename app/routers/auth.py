from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm

from app.core.security import (
    get_current_user,
    hash_password,
    issue_token_pair,
    revoke_refresh_token,
    validate_refresh_token,
    verify_password,
)
from app.models.user import Address, User
from app.schemas.token import RefreshTokenRequest, Token
from app.schemas.user import UserRegisterRequest, UserResponse

router = APIRouter(
    prefix="/auth",
    tags=["Authentication"],
)


@router.post("/register", status_code=status.HTTP_201_CREATED, response_model=UserResponse)
async def register(request: UserRegisterRequest):
    """Register a new user in the system."""
    existing_user = await User.find_one(User.email == request.email)
    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email is already registered.",
        )

    new_user = User(
        email=request.email,
        hashed_password=hash_password(request.password),
        full_name=request.full_name,
    )
    await new_user.insert()

    return UserResponse(
        id=str(new_user.id),
        email=new_user.email,
        full_name=new_user.full_name,
        role=new_user.role,
        is_active=new_user.is_active,
    )


@router.post("/login", response_model=Token)
async def login(form_data: OAuth2PasswordRequestForm = Depends()):
    """
    Authenticate user and return access + refresh tokens.
    OAuth2 uses 'username' as the field name; pass the user's email there.
    """
    user = await User.find_one(User.email == form_data.username)

    if not user or not verify_password(form_data.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account is inactive",
        )

    access_token, refresh_token = await issue_token_pair(user)

    return {
        "access_token": access_token,
        "refresh_token": refresh_token,
        "token_type": "bearer",
    }


@router.post("/refresh", response_model=Token)
async def refresh_tokens(request: RefreshTokenRequest):
    """Exchange a valid refresh token for a new access + refresh token pair."""
    user = await validate_refresh_token(request.refresh_token)
    await revoke_refresh_token(request.refresh_token)

    access_token, refresh_token = await issue_token_pair(user)

    return {
        "access_token": access_token,
        "refresh_token": refresh_token,
        "token_type": "bearer",
    }


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(request: RefreshTokenRequest):
    """Revoke a refresh token so it can no longer be used."""
    await revoke_refresh_token(request.refresh_token)


@router.get("/me", response_model=UserResponse)
async def get_my_profile(current_user: User = Depends(get_current_user)):
    """Get the currently logged-in user's profile."""
    return UserResponse(
        id=str(current_user.id),
        email=current_user.email,
        full_name=current_user.full_name,
        role=current_user.role,
        is_active=current_user.is_active,
        addresses=current_user.addresses,
    )


@router.post("/me/addresses", response_model=UserResponse)
async def add_address(
    new_address: Address,
    current_user: User = Depends(get_current_user),
):
    """Add a new address to the currently logged-in user's profile."""
    current_user.addresses.append(new_address)
    await current_user.save()

    return UserResponse(
        id=str(current_user.id),
        email=current_user.email,
        full_name=current_user.full_name,
        role=current_user.role,
        is_active=current_user.is_active,
        addresses=current_user.addresses,
    )
