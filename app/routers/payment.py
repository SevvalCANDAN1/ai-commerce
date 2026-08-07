import secrets

from fastapi import APIRouter, Depends, Header, HTTPException, status

from app.core.security import get_current_user
from app.models.user import User
from app.schemas.payment import MockPaymentRequest, MockPaymentResponse
from app.services.order_service import (
    finalize_paid_order,
    get_checkout_session_for_user,
    get_idempotent_response,
    simulate_mock_payment_failure,
    store_idempotent_response,
)

router = APIRouter(
    prefix="/payment",
    tags=["Payment"],
)


@router.post("/mock", response_model=MockPaymentResponse)
async def mock_payment(
    request: MockPaymentRequest,
    current_user: User = Depends(get_current_user),
    idempotency_key: str = Header(..., alias="Idempotency-Key", min_length=1),
):
    """Process a mock payment with chaos injection and idempotency protection."""
    endpoint = "/api/v1/payment/mock"
    existing = await get_idempotent_response(idempotency_key)
    if existing is not None and existing.endpoint == endpoint:
        return MockPaymentResponse(**existing.response_body)

    checkout_session = await get_checkout_session_for_user(request.checkout_session_id, current_user)

    failure_reason = simulate_mock_payment_failure()
    if failure_reason is not None:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Mock payment failed: {failure_reason}",
        )

    payment_id = f"pay_mock_{secrets.token_hex(8)}"
    order = await finalize_paid_order(checkout_session, payment_id=payment_id)

    response = MockPaymentResponse(
        payment_id=payment_id,
        order_id=str(order.id),
        order_number=order.order_number,
        status=order.status.value,
        grand_total=order.pricing_snapshot.grand_total,
    )
    await store_idempotent_response(
        key=idempotency_key,
        endpoint=endpoint,
        response_body=response.model_dump(),
        status_code=status.HTTP_200_OK,
    )
    return response
