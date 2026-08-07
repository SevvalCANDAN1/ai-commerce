from fastapi import Depends, Header, HTTPException, status
from fastapi.security import OAuth2PasswordBearer

from app.core.security import get_current_user
from app.models.user import User

oauth2_scheme_optional = OAuth2PasswordBearer(
    tokenUrl="/api/v1/auth/login",
    auto_error=False,
)


async def get_optional_user(
    token: str | None = Depends(oauth2_scheme_optional),
) -> User | None:
    if token is None:
        return None
    try:
        return await get_current_user(token)
    except HTTPException:
        return None


class CartOwner:
    def __init__(self, user: User | None = None, guest_id: str | None = None):
        self.user = user
        self.guest_id = guest_id

    @property
    def is_authenticated(self) -> bool:
        return self.user is not None


async def resolve_cart_owner(
    current_user: User | None = Depends(get_optional_user),
    x_guest_id: str | None = Header(default=None, alias="X-Guest-Id"),
) -> CartOwner:
    if current_user is not None:
        return CartOwner(user=current_user, guest_id=None)
    if x_guest_id:
        return CartOwner(user=None, guest_id=x_guest_id)
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Authentication required or X-Guest-Id header must be provided",
    )
