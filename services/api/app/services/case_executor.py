from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import models
from app.domain.enums import AuditEventType, Decision, RemedyStatus
from app.domain.ids import new_id
from app.schemas.claims import CompiledClaim
from app.schemas.execution import CaseExecutionResponse
from app.schemas.refunds import CashRefundResponse
from app.services.case_evaluator import CaseEvaluator
from app.services.exceptions import PaymentNotFound
from app.services.refund_executor import RefundExecutor


class CaseExecutor:
    """Deterministic money path after policy. AI does not run here."""

    def __init__(self, session: Session, evaluator: CaseEvaluator, refunds: RefundExecutor) -> None:
        self.session = session
        self.evaluator = evaluator
        self.refunds = refunds

    def execute(self, claim_id: str) -> CaseExecutionResponse:
        evaluation = self.evaluator.evaluate(claim_id)
        record = self.session.get(models.CompiledClaimRecord, claim_id)
        assert record is not None
        if evaluation.decision.decision is not Decision.ALLOW:
            self._audit(
                record.merchant_id,
                evaluation.remedy_request_id,
                AuditEventType.REMEDY_EXECUTION_BLOCKED,
                {
                    "claim_id": claim_id,
                    "decision": evaluation.decision.decision.value,
                    "incident_id": evaluation.incident_id,
                },
            )
            return CaseExecutionResponse(
                evaluation=evaluation,
                executed=False,
                blocked_reason=evaluation.decision.decision.value,
            )

        claim = CompiledClaim.model_validate(record.payload)
        payment = self._payment_for(record, claim)
        current = self.session.get(models.RemedyRequest, evaluation.remedy_request_id)
        assert current is not None
        row = self.refunds.execute_cash_refund(
            record.merchant_id,
            evaluation.incident_id,
            payment.razorpay_payment_id,
            current.entitlement_consumption_minor,
            f"exec_{current.id}",
        )
        if row.status == RemedyStatus.SETTLED.value:
            current.status = RemedyStatus.SETTLED.value
        elif row.status == RemedyStatus.FAILED.value:
            current.status = RemedyStatus.FAILED.value
        elif row.status == RemedyStatus.RECONCILIATION_REQUIRED.value:
            current.status = RemedyStatus.RECONCILIATION_REQUIRED.value
        else:
            current.status = RemedyStatus.PROCESSING.value
        self._audit(
            record.merchant_id,
            current.id,
            AuditEventType.REMEDY_EXECUTED,
            {
                "claim_id": claim_id,
                "refund_id": row.id,
                "razorpay_refund_id": row.razorpay_refund_id,
                "status": row.status,
            },
        )
        self.session.flush()
        return CaseExecutionResponse(
            evaluation=evaluation,
            executed=True,
            refund=CashRefundResponse(
                refund_id=row.id,
                razorpay_refund_id=row.razorpay_refund_id,
                status=RemedyStatus(row.status),
                amount_minor=row.amount_minor,
                idempotency_key=row.idempotency_key,
            ),
        )

    def _payment_for(self, record: models.CompiledClaimRecord, claim: CompiledClaim) -> models.RazorpayPayment:
        message = self.session.get(models.SupportMessage, record.support_message_id)
        order_id = claim.order_reference or (message.order_reference if message is not None else None)
        query = select(models.RazorpayPayment).where(models.RazorpayPayment.merchant_id == record.merchant_id)
        if order_id is not None:
            query = query.where(models.RazorpayPayment.internal_order_id == order_id)
        payment = self.session.scalars(query).first()
        if payment is None:
            raise PaymentNotFound(order_id or record.merchant_id)
        return payment

    def _audit(
        self,
        merchant_id: str,
        remedy_request_id: str,
        event_type: AuditEventType,
        payload: dict,
    ) -> None:
        self.session.add(
            models.AuditEvent(
                id=new_id("aud"),
                merchant_id=merchant_id,
                event_type=event_type.value,
                remedy_request_id=remedy_request_id,
                payload=payload,
            )
        )
