from pydantic import BaseModel, Field

from app.domain.enums import Channel, IncidentType
from app.domain.money import MinorUnits


class ExtractedFact(BaseModel):
    field: str = Field(min_length=1)
    value: str
    source_text: str = Field(min_length=1)


class ClaimDraft(BaseModel):
    """Model output only. Must not include claim_id, customer_id, or channel."""

    order_reference: str | None = None
    product_reference: str | None = None
    unit_reference: str | None = None
    incident_type: IncidentType | None = None
    incident_description: str = Field(min_length=1)
    incident_time: str | None = None
    affected_quantity: int | None = Field(default=None, ge=1)
    requested_remedy: str | None = None
    requested_amount_minor: MinorUnits | None = None
    extracted_facts: list[ExtractedFact] = []
    unknown_fields: list[str] = []
    model_confidence: float | None = Field(default=None, ge=0.0, le=1.0)


class CompiledClaim(BaseModel):
    """Grounded claim. Policy and the ledger must not treat this as money authority."""

    claim_id: str = Field(min_length=1)
    customer_id: str = Field(min_length=1)
    channel: Channel
    order_reference: str | None = None
    product_reference: str | None = None
    unit_reference: str | None = None
    incident_type: IncidentType | None = None
    incident_description: str = Field(min_length=1)
    incident_time: str | None = None
    affected_quantity: int | None = Field(default=None, ge=1)
    requested_remedy: str | None = None
    requested_amount_minor: MinorUnits | None = None
    extracted_facts: list[ExtractedFact] = []
    unknown_fields: list[str] = []
    model_confidence: float | None = Field(default=None, ge=0.0, le=1.0)


class CompileClaimRequest(BaseModel):
    support_message_id: str = Field(min_length=1)


class CompileClaimResponse(BaseModel):
    claim: CompiledClaim
    replayed: bool
    audit_id: str
