from pydantic import BaseModel, Field

from app.domain.enums import RemedyStatus
from app.domain.money import MinorUnits


class CashRefundRequest(BaseModel):
    merchant_id: str = Field(min_length=1)
    incident_id: str = Field(min_length=1)
    razorpay_payment_id: str = Field(min_length=1)
    amount_minor: MinorUnits
    idempotency_key: str = Field(min_length=10, pattern=r"^[A-Za-z0-9_-]+$")


class CashRefundResponse(BaseModel):
    refund_id: str
    razorpay_refund_id: str | None
    status: RemedyStatus
    amount_minor: int
    idempotency_key: str
