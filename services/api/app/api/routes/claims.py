from fastapi import APIRouter, Depends, HTTPException

from app.api.deps import get_claim_compiler
from app.schemas.claims import CompiledClaim, CompileClaimRequest, CompileClaimResponse
from app.services.claim_compiler import ClaimCompiler
from app.services.exceptions import IngestError

router = APIRouter(prefix="/v1/claims", tags=["claims"])


@router.post("/compile", response_model=CompileClaimResponse)
def compile_claim(
    request: CompileClaimRequest,
    compiler: ClaimCompiler = Depends(get_claim_compiler),
) -> CompileClaimResponse:
    try:
        return compiler.compile_message(request.support_message_id)
    except IngestError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message) from exc


@router.get("/{claim_id}", response_model=CompiledClaim)
def get_claim(
    claim_id: str,
    compiler: ClaimCompiler = Depends(get_claim_compiler),
) -> CompiledClaim:
    try:
        return compiler.get_claim(claim_id)
    except IngestError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message) from exc
