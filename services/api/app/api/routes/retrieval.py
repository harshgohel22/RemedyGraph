from fastapi import APIRouter, Depends, HTTPException, Query

from app.api.deps import get_candidate_retrieval
from app.schemas.retrieval import RetrievalResponse
from app.services.candidate_retrieval import DEFAULT_LIMIT, MAX_LIMIT, CandidateRetrieval
from app.services.exceptions import IngestError

router = APIRouter(prefix="/v1/claims", tags=["retrieval"])


@router.get("/{claim_id}/candidates", response_model=RetrievalResponse)
def retrieve_candidates(
    claim_id: str,
    limit: int = Query(default=DEFAULT_LIMIT, ge=1, le=MAX_LIMIT),
    retrieval: CandidateRetrieval = Depends(get_candidate_retrieval),
) -> RetrievalResponse:
    try:
        return retrieval.retrieve(claim_id, limit=limit)
    except IngestError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message) from exc
