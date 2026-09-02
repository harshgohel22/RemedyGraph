from pydantic import BaseModel, Field

from app.domain.enums import IncidentRelation
from app.domain.money import MinorUnits


class EntitlementPosition(BaseModel):
    """Current money state for one incident. remaining is derived, never stored as a float."""

    incident_id: str = Field(min_length=1)
    allowed_entitlement_minor: MinorUnits
    settled_entitlement_minor: MinorUnits
    reserved_entitlement_minor: MinorUnits

    def remaining_minor(self) -> int:
        return (
            self.allowed_entitlement_minor
            - self.settled_entitlement_minor
            - self.reserved_entitlement_minor
        )


class IncidentLinkAssessment(BaseModel):
    """Linker output. Policy may read relation; it must not let this object move money."""

    claim_id: str = Field(min_length=1)
    candidate_incident_id: str = Field(min_length=1)
    relation: IncidentRelation
    confidence: float = Field(ge=0.0, le=1.0)
    evidence_for: list[str] = []
    evidence_against: list[str] = []
    contradictory_fields: list[str] = []
    requires_review: bool = False
    model_version: str | None = None
    prompt_version: str | None = None


class LinkDraft(BaseModel):
    """Model output only. Must not include claim_id or incident ids."""

    relation: IncidentRelation
    confidence: float = Field(ge=0.0, le=1.0)
    evidence_for: list[str] = []
    evidence_against: list[str] = []
    contradictory_fields: list[str] = []
    requires_review: bool = False


class LinkClaimResponse(BaseModel):
    primary: IncidentLinkAssessment
    assessments: list[IncidentLinkAssessment]
    replayed: bool
    audit_id: str | None = None
