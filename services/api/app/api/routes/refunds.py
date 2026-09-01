from fastapi import APIRouter, Depends, HTTPException

from app.api.deps import get_refund_executor
from app.domain.enums import RemedyStatus
from app.schemas.refunds import CashRefundRequest, CashRefundResponse
from app.services.exceptions import IngestError
from app.services.refund_executor import RefundExecutor
from app.services.entitlement_ledger import LedgerError
from app.services.razorpay_client import RazorpayRejected

router = APIRouter(prefix="/v1/refunds", tags=["refunds"])


@router.post("", response_model=CashRefundResponse)
def create_cash_refund(
    request: CashRefundRequest,
    executor: RefundExecutor = Depends(get_refund_executor),
) -> CashRefundResponse:
    try:
        row = executor.execute_cash_refund(
            request.merchant_id,
            request.incident_id,
            request.razorpay_payment_id,
            request.amount_minor,
            request.idempotency_key,
        )
    except IngestError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message) from exc
    except LedgerError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except RazorpayRejected as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return CashRefundResponse(
        refund_id=row.id,
        razorpay_refund_id=row.razorpay_refund_id,
        status=RemedyStatus(row.status),
        amount_minor=row.amount_minor,
        idempotency_key=row.idempotency_key,
    )
