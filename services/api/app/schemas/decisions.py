from pydantic import BaseModel, Field

from app.domain.enums import Decision, ReasonCode
from app.domain.money import MinorUnits


class PolicyDecision(BaseModel):
    decision_id: str = Field(min_length=1)
    decision: Decision
    reason_codes: list[ReasonCode]
    incident_id: str = Field(min_length=1)
    allowed_entitlement_minor: MinorUnits
    settled_entitlement_minor: MinorUnits
    reserved_entitlement_minor: MinorUnits
    remaining_before_minor: int
    proposed_consumption_minor: MinorUnits
    remaining_after_minor: int
    avoidable_overcompensation_minor: int
    max_safe_amount_minor: int
    semantic_confidence: float | None = None
    audit_id: str | None = None
