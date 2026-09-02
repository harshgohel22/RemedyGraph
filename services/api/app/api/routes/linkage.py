from fastapi import APIRouter, Depends, HTTPException

from app.api.deps import get_incident_link_service
from app.schemas.incidents import LinkClaimResponse
from app.services.exceptions import IngestError
from app.services.incident_link_service import IncidentLinkService

router = APIRouter(prefix="/v1/claims", tags=["linkage"])


@router.post("/{claim_id}/link", response_model=LinkClaimResponse)
def link_claim(
    claim_id: str,
    service: IncidentLinkService = Depends(get_incident_link_service),
) -> LinkClaimResponse:
    try:
        return service.link_claim(claim_id)
    except IngestError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message) from exc


@router.get("/{claim_id}/link", response_model=LinkClaimResponse)
def get_link(
    claim_id: str,
    service: IncidentLinkService = Depends(get_incident_link_service),
) -> LinkClaimResponse:
    try:
        return service.get_link(claim_id)
    except IngestError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message) from exc
