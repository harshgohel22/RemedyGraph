from pydantic import BaseModel, Field

from app.domain.enums import Currency, RemedyType
from app.domain.money import MinorUnits


class RemedyProposal(BaseModel):
    remedy_request_id: str = Field(min_length=1)
    claim_id: str | None = None
    remedy_type: RemedyType
    amount_minor: MinorUnits
    entitlement_consumption_minor: MinorUnits
    merchant_cost_minor: MinorUnits | None = None
    currency: Currency = Currency.INR
    idempotency_key: str = Field(min_length=10, pattern=r"^[A-Za-z0-9_-]+$")
