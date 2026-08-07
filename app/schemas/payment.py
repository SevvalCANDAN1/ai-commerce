from pydantic import BaseModel, Field


class MockPaymentRequest(BaseModel):
    checkout_session_id: str = Field(..., min_length=1)


class MockPaymentResponse(BaseModel):
    payment_id: str
    order_id: str
    order_number: str
    status: str
    grand_total: float
