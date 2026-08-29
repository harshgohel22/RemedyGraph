from fastapi import APIRouter, HTTPException

from app.evaluation.scenario_schema import PolicyEvaluationRequest
from app.schemas.decisions import PolicyDecision
from app.schemas.incidents import EntitlementPosition
from app.services.policy_engine import PolicyInvariantError, decide

router = APIRouter(prefix="/v1/evaluate", tags=["evaluate"])


@router.post("/scenario", response_model=PolicyDecision)
def evaluate_scenario(scenario: PolicyEvaluationRequest) -> PolicyDecision:
    """Run policy on a fully structured scenario. expected is ignored — tests assert it."""
    position = EntitlementPosition(
        incident_id=scenario.incident_id,
        allowed_entitlement_minor=scenario.allowed_entitlement_minor,
        settled_entitlement_minor=scenario.settled_entitlement_minor,
        reserved_entitlement_minor=scenario.reserved_entitlement_minor,
    )
    try:
        return decide(
            position,
            scenario.relation,
            scenario.proposed_consumption_minor,
            requires_review=scenario.requires_review,
            contradictory_fields=scenario.contradictory_fields,
            semantic_confidence=scenario.semantic_confidence,
        )
    except PolicyInvariantError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
