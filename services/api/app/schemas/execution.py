from pydantic import BaseModel

from app.schemas.decisions import CaseEvaluationResponse
from app.schemas.refunds import CashRefundResponse


class CaseExecutionResponse(BaseModel):
    """Evaluate, then refund only if policy ALLOWED. Money still goes through the ledger."""

    evaluation: CaseEvaluationResponse
    executed: bool
    blocked_reason: str | None = None
    refund: CashRefundResponse | None = None
