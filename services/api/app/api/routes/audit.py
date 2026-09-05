from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import models
from app.db.session import get_db
from app.schemas.audit import AuditEventOut, AuditListResponse

router = APIRouter(prefix="/v1/audit", tags=["audit"])


@router.get("", response_model=AuditListResponse)
def list_audit_events(
    merchant_id: str,
    limit: int = Query(default=50, ge=1, le=200),
    session: Session = Depends(get_db),
) -> AuditListResponse:
    merchant = session.get(models.Merchant, merchant_id)
    if merchant is None:
        raise HTTPException(status_code=404, detail=f"merchant not found: {merchant_id}")
    rows = list(
        session.scalars(
            select(models.AuditEvent)
            .where(models.AuditEvent.merchant_id == merchant_id)
            .order_by(models.AuditEvent.created_at.asc())
            .limit(limit)
        ).all()
    )
    return AuditListResponse(
        merchant_id=merchant_id,
        events=[AuditEventOut.model_validate(row) for row in rows],
    )
