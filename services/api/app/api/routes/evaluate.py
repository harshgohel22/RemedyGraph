from fastapi import APIRouter, Depends, HTTPException

from app.api.deps import get_case_evaluator, get_case_executor
from app.evaluation.scenario_schema import PolicyEvaluationRequest
from app.schemas.decisions import CaseEvaluationResponse, PolicyDecision
from app.schemas.execution import CaseExecutionResponse
from app.schemas.incidents import EntitlementPosition
from app.services.case_evaluator import CaseEvaluator
from app.services.case_executor import CaseExecutor
from app.services.entitlement_ledger import LedgerError
from app.services.exceptions import IngestError
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


@router.post("/claims/{claim_id}", response_model=CaseEvaluationResponse)
def evaluate_claim(
    claim_id: str,
    evaluator: CaseEvaluator = Depends(get_case_evaluator),
) -> CaseEvaluationResponse:
    try:
        return evaluator.evaluate(claim_id)
    except IngestError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message) from exc
    except (PolicyInvariantError, LedgerError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post("/claims/{claim_id}/execute", response_model=CaseExecutionResponse)
def execute_claim(
    claim_id: str,
    executor: CaseExecutor = Depends(get_case_executor),
) -> CaseExecutionResponse:
    try:
        return executor.execute(claim_id)
    except IngestError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message) from exc
    except (PolicyInvariantError, LedgerError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
