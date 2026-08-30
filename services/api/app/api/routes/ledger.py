from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.incidents import EntitlementPosition
from app.schemas.ledger import (
    EntitlementResponse,
    OpenEntitlementRequest,
    ReservationActionRequest,
    ReservationResponse,
    ReserveRequest,
)
from app.services.entitlement_ledger import (
    EntitlementExists,
    IncidentNotFound,
    InsufficientEntitlement,
    LedgerError,
    ReservationNotActive,
    ReservationRecord,
)
from app.services.exceptions import IdempotencyConflict, IngestError
from app.services.ledger_service import LedgerService

router = APIRouter(prefix="/v1/ledger", tags=["ledger"])


def get_ledger(session: Session = Depends(get_db)) -> LedgerService:
    return LedgerService(session)


def _http(exc: Exception) -> HTTPException:
    if isinstance(exc, IngestError):
        return HTTPException(status_code=exc.status_code, detail=exc.message)
    if isinstance(exc, IncidentNotFound):
        return HTTPException(status_code=404, detail=str(exc))
    if isinstance(exc, (InsufficientEntitlement, EntitlementExists, ReservationNotActive)):
        return HTTPException(status_code=409, detail=str(exc))
    if isinstance(exc, LedgerError):
        return HTTPException(status_code=422, detail=str(exc))
    return HTTPException(status_code=500, detail="ledger error")


def _reservation(record: ReservationRecord) -> ReservationResponse:
    return ReservationResponse(
        incident_id=record.incident_id,
        remedy_request_id=record.remedy_request_id,
        idempotency_key=record.idempotency_key,
        amount_minor=record.amount_minor,
        status=record.status,
    )


def _entitlement(position: EntitlementPosition) -> EntitlementResponse:
    return EntitlementResponse(
        incident_id=position.incident_id,
        allowed_entitlement_minor=position.allowed_entitlement_minor,
        settled_entitlement_minor=position.settled_entitlement_minor,
        reserved_entitlement_minor=position.reserved_entitlement_minor,
        remaining_minor=position.remaining_minor(),
    )


@router.post("/entitlements", response_model=EntitlementResponse)
def open_entitlement(
    request: OpenEntitlementRequest,
    ledger: LedgerService = Depends(get_ledger),
) -> EntitlementResponse:
    try:
        position = ledger.open_incident(
            request.merchant_id,
            request.incident_id,
            request.allowed_entitlement_minor,
        )
        return _entitlement(position)
    except Exception as exc:
        if isinstance(exc, (LedgerError, IngestError)):
            raise _http(exc) from exc
        raise


@router.get("/entitlements/{incident_id}", response_model=EntitlementResponse)
def get_entitlement(
    incident_id: str,
    merchant_id: str,
    ledger: LedgerService = Depends(get_ledger),
) -> EntitlementResponse:
    try:
        return _entitlement(ledger.get_position(merchant_id, incident_id))
    except Exception as exc:
        if isinstance(exc, (LedgerError, IngestError)):
            raise _http(exc) from exc
        raise


@router.post("/reservations", response_model=ReservationResponse)
def reserve(
    request: ReserveRequest,
    ledger: LedgerService = Depends(get_ledger),
) -> ReservationResponse:
    try:
        record = ledger.reserve(
            request.merchant_id,
            request.incident_id,
            request.amount_minor,
            request.idempotency_key,
            request.remedy_request_id,
        )
        return _reservation(record)
    except Exception as exc:
        if isinstance(exc, (LedgerError, IngestError)):
            raise _http(exc) from exc
        raise


@router.post("/reservations/settle", response_model=ReservationResponse)
def settle(
    request: ReservationActionRequest,
    ledger: LedgerService = Depends(get_ledger),
) -> ReservationResponse:
    try:
        return _reservation(ledger.settle(request.merchant_id, request.idempotency_key))
    except Exception as exc:
        if isinstance(exc, (LedgerError, IngestError)):
            raise _http(exc) from exc
        raise


@router.post("/reservations/release", response_model=ReservationResponse)
def release(
    request: ReservationActionRequest,
    ledger: LedgerService = Depends(get_ledger),
) -> ReservationResponse:
    try:
        return _reservation(ledger.release(request.merchant_id, request.idempotency_key))
    except Exception as exc:
        if isinstance(exc, (LedgerError, IngestError)):
            raise _http(exc) from exc
        raise


@router.post("/reservations/fail", response_model=ReservationResponse)
def fail(
    request: ReservationActionRequest,
    ledger: LedgerService = Depends(get_ledger),
) -> ReservationResponse:
    try:
        return _reservation(ledger.fail(request.merchant_id, request.idempotency_key))
    except Exception as exc:
        if isinstance(exc, (LedgerError, IngestError)):
            raise _http(exc) from exc
        raise
