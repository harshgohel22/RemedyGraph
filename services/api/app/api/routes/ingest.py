from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.ingest import IngestAttemptRequest, IngestAttemptResponse, StoredAttempt
from app.schemas.world import WorldIngestRequest, WorldIngestResponse
from app.services.exceptions import IngestError
from app.services.ingest_service import IngestService

router = APIRouter(prefix="/v1/ingest", tags=["ingest"])


def get_ingest_service(session: Session = Depends(get_db)) -> IngestService:
    return IngestService(session)


@router.post("/world", response_model=WorldIngestResponse)
def ingest_world(
    request: WorldIngestRequest,
    service: IngestService = Depends(get_ingest_service),
) -> WorldIngestResponse:
    try:
        return service.ingest_world(request)
    except IngestError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message) from exc


@router.post("/attempts", response_model=IngestAttemptResponse)
def ingest_attempt(
    request: IngestAttemptRequest,
    service: IngestService = Depends(get_ingest_service),
) -> IngestAttemptResponse:
    try:
        return service.ingest_attempt(request)
    except IngestError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message) from exc


@router.get("/attempts/{remedy_request_id}", response_model=StoredAttempt)
def get_attempt(
    remedy_request_id: str,
    service: IngestService = Depends(get_ingest_service),
) -> StoredAttempt:
    try:
        return service.get_attempt(remedy_request_id)
    except IngestError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message) from exc
