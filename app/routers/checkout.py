from fastapi import APIRouter, Depends, status

from app.core.security import get_current_user
from app.models.user import User
from app.schemas.checkout import CheckoutPreviewRequest, CheckoutSessionResponse
from app.services.order_service import create_checkout_preview, get_checkout_session_for_user

router = APIRouter(
    prefix="/checkout",
    tags=["Checkout"],
)


def _to_checkout_response(session) -> CheckoutSessionResponse:
    return CheckoutSessionResponse(
        id=str(session.id),
        address_snapshot=session.address_snapshot,
        items_snapshot=session.items_snapshot,
        pricing_snapshot=session.pricing_snapshot,
        coupon_code=session.coupon_code,
        expires_at=session.expires_at,
        consumed=session.consumed,
    )


@router.post("/preview", response_model=CheckoutSessionResponse, status_code=status.HTTP_201_CREATED)
async def checkout_preview(
    request: CheckoutPreviewRequest,
    current_user: User = Depends(get_current_user),
):
    """Validate cart, copy address snapshot, reserve stock, and return checkout session."""
    session = await create_checkout_preview(
        user=current_user,
        address_index=request.address_index,
        coupon_code=request.coupon_code,
    )
    return _to_checkout_response(session)


@router.get("/{session_id}", response_model=CheckoutSessionResponse)
async def get_checkout_session(
    session_id: str,
    current_user: User = Depends(get_current_user),
):
    """Return an active checkout session owned by the current user."""
    session = await get_checkout_session_for_user(session_id, current_user)
    return _to_checkout_response(session)
