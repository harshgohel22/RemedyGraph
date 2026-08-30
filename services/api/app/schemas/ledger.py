from pydantic import BaseModel, Field

from app.domain.enums import RemedyStatus
from app.domain.money import MinorUnits


class OpenEntitlementRequest(BaseModel):
    merchant_id: str = Field(min_length=1)
    incident_id: str = Field(min_length=1)
    allowed_entitlement_minor: MinorUnits


class ReserveRequest(BaseModel):
    merchant_id: str = Field(min_length=1)
    incident_id: str = Field(min_length=1)
    amount_minor: MinorUnits
    idempotency_key: str = Field(min_length=10, pattern=r"^[A-Za-z0-9_-]+$")
    remedy_request_id: str | None = None


class ReservationActionRequest(BaseModel):
    merchant_id: str = Field(min_length=1)
    idempotency_key: str = Field(min_length=10, pattern=r"^[A-Za-z0-9_-]+$")


class ReservationResponse(BaseModel):
    incident_id: str
    remedy_request_id: str
    idempotency_key: str
    amount_minor: int
    status: RemedyStatus


class EntitlementResponse(BaseModel):
    incident_id: str
    allowed_entitlement_minor: int
    settled_entitlement_minor: int
    reserved_entitlement_minor: int
    remaining_minor: int
