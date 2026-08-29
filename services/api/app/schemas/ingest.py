from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.domain.enums import Channel, Currency, RemedyStatus, RemedyType
from app.domain.money import MinorUnits


class SupportMessageIn(BaseModel):
    """Raw inbound message. Unknown identifiers stay null; ingest must not fill them."""

    merchant_id: str = Field(min_length=1)
    customer_id: str = Field(min_length=1)
    channel: Channel
    body: str = Field(min_length=1)
    occurred_at: datetime
    order_reference: str | None = None
    external_message_id: str | None = None

    @field_validator("order_reference", "external_message_id", mode="before")
    @classmethod
    def blank_to_none(cls, value: object) -> object:
        if value == "":
            return None
        return value


class RemedyProposalIn(BaseModel):
    remedy_type: RemedyType
    amount_minor: MinorUnits
    entitlement_consumption_minor: MinorUnits
    merchant_cost_minor: MinorUnits | None = None
    currency: Currency = Currency.INR
    idempotency_key: str = Field(min_length=10, pattern=r"^[A-Za-z0-9_-]+$")


class IngestAttemptRequest(BaseModel):
    message: SupportMessageIn
    proposal: RemedyProposalIn


class IngestAttemptResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    support_message_id: str
    remedy_request_id: str
    audit_id: str
    status: RemedyStatus
    order_reference: str | None
    incident_id: str | None
    replayed: bool


class StoredAttempt(BaseModel):
    remedy_request_id: str
    support_message_id: str
    merchant_id: str
    customer_id: str
    channel: Channel
    body: str
    order_reference: str | None
    remedy_type: RemedyType
    amount_minor: int
    entitlement_consumption_minor: int
    merchant_cost_minor: int | None
    currency: Currency
    idempotency_key: str
    status: RemedyStatus
    incident_id: str | None
    occurred_at: datetime
