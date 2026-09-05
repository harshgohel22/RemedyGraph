from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.exc import IntegrityError

from app.api.deps import get_demo_service
from app.schemas.demo import DemoRunRequest, DemoRunResponse, DemoScenarioInfo
from app.services.demo_service import DemoService
from app.services.exceptions import IngestError
from app.services.entitlement_ledger import LedgerError
from app.services.policy_engine import PolicyInvariantError

router = APIRouter(prefix="/v1/demo", tags=["demo"])


@router.get("/scenarios", response_model=list[DemoScenarioInfo])
def list_demo_scenarios(demo: DemoService = Depends(get_demo_service)) -> list[DemoScenarioInfo]:
    return demo.list_scenarios()


@router.post("/run", response_model=DemoRunResponse)
def run_demo_scenario(
    request: DemoRunRequest,
    demo: DemoService = Depends(get_demo_service),
) -> DemoRunResponse:
    try:
        return demo.run(request.scenario_id)
    except IngestError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message) from exc
    except (PolicyInvariantError, LedgerError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except IntegrityError as exc:
        raise HTTPException(
            status_code=409,
            detail="Demo world collided with leftover rows. Stop the API, delete remedygraph.db, and start again.",
        ) from exc
