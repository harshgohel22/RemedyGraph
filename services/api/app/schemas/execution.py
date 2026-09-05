from pydantic import BaseModel

from app.domain.enums import RemedyStatus, RemedyType
from app.schemas.decisions import CaseEvaluationResponse
from app.schemas.refunds import CashRefundResponse


class SimulatedRemedy(BaseModel):
    remedy_type: RemedyType
    status: RemedyStatus
    amount_minor: int
    replacement_unit_id: str | None = None


class CaseExecutionResponse(BaseModel):
    """Evaluate, then refund or simulate only if policy ALLOWED. Money still goes through the ledger."""

    evaluation: CaseEvaluationResponse
    executed: bool
    blocked_reason: str | None = None
    refund: CashRefundResponse | None = None
    simulated: SimulatedRemedy | None = None
