from pydantic import BaseModel, ConfigDict, Field

from app.domain.enums import Decision, IncidentRelation, RemedyType
from app.domain.money import MinorUnits


class ExpectedPolicyResult(BaseModel):
    decision: Decision
    remaining_before_minor: int
    remaining_after_minor: int
    avoidable_overcompensation_minor: int
    max_safe_amount_minor: int


class PolicyEvaluationRequest(BaseModel):
    """Structured inputs only. extra=ignore so seed JSON can include expected."""

    model_config = ConfigDict(extra="ignore")

    scenario_id: str = Field(min_length=1)
    family: str = Field(min_length=1)
    incident_id: str = Field(min_length=1)
    relation: IncidentRelation
    requires_review: bool = False
    contradictory_fields: list[str] = []
    allowed_entitlement_minor: MinorUnits
    settled_entitlement_minor: MinorUnits
    reserved_entitlement_minor: MinorUnits
    proposed_consumption_minor: MinorUnits
    remedy_type: RemedyType
    amount_minor: MinorUnits
    semantic_confidence: float | None = Field(default=None, ge=0.0, le=1.0)


class SeedScenario(PolicyEvaluationRequest):
    expected: ExpectedPolicyResult


class SeedScenarioFile(BaseModel):
    scenarios: list[SeedScenario]
