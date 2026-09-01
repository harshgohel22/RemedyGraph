from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import models
from app.domain.enums import AuditEventType, RemedyStatus
from app.domain.ids import new_id
from app.services.exceptions import PaymentNotFound, PaymentNotRefundable
from app.services.ledger_service import LedgerService
from app.services.razorpay_client import (
    RazorpayGateway,
    RazorpayRejected,
    RazorpayTimeout,
    RefundResult,
)


class RefundExecutor:
    def __init__(self, session: Session, gateway: RazorpayGateway) -> None:
        self.session = session
        self.gateway = gateway
        self.ledger = LedgerService(session)

    def execute_cash_refund(
        self,
        merchant_id: str,
        incident_id: str,
        razorpay_payment_id: str,
        amount_minor: int,
        idempotency_key: str,
    ) -> models.RazorpayRefund:
        payment = self._require_captured_payment(merchant_id, razorpay_payment_id, amount_minor)
        existing = self._refund_by_key(merchant_id, idempotency_key)
        if existing is not None:
            return self._resume(existing)

        self.ledger.reserve(
            merchant_id,
            incident_id,
            amount_minor,
            idempotency_key,
        )
        try:
            result = self.gateway.create_refund(
                payment.razorpay_payment_id,
                amount_minor,
                idempotency_key,
            )
        except RazorpayTimeout:
            row = self._save_refund(
                merchant_id,
                incident_id,
                payment.id,
                amount_minor,
                idempotency_key,
                razorpay_refund_id=None,
                status=RemedyStatus.RECONCILIATION_REQUIRED.value,
            )
            self._audit(merchant_id, AuditEventType.REFUND_REQUESTED, row, {"timeout": True})
            return row
        except RazorpayRejected:
            self.ledger.fail(merchant_id, idempotency_key)
            raise

        row = self._save_refund(
            merchant_id,
            incident_id,
            payment.id,
            amount_minor,
            idempotency_key,
            razorpay_refund_id=result.razorpay_refund_id,
            status=RemedyStatus.PROCESSING.value,
        )
        self._audit(merchant_id, AuditEventType.REFUND_REQUESTED, row, {"razorpay_status": result.status})
        if result.status == "processed":
            self._settle(merchant_id, idempotency_key, row)
        elif result.status == "failed":
            self.ledger.fail(merchant_id, idempotency_key)
            row.status = RemedyStatus.FAILED.value
            self.session.flush()
        return row

    def apply_gateway_status(self, merchant_id: str, result: RefundResult) -> models.RazorpayRefund | None:
        row = self._refund_by_razorpay_id(result.razorpay_refund_id)
        if row is None:
            row = self._refund_by_key(merchant_id, result.idempotency_key) if result.idempotency_key else None
        if row is None:
            return None
        row.razorpay_refund_id = result.razorpay_refund_id
        row.status = self._map_status(result.status)
        if result.status == "processed":
            self._settle(row.merchant_id, row.idempotency_key, row)
        elif result.status == "failed":
            reservation = self.ledger.get_reservation(row.merchant_id, row.idempotency_key)
            if reservation is not None and reservation.status is RemedyStatus.RESERVED:
                self.ledger.fail(row.merchant_id, row.idempotency_key)
            row.status = RemedyStatus.FAILED.value
        self.session.flush()
        return row

    def _resume(self, existing: models.RazorpayRefund) -> models.RazorpayRefund:
        if existing.status == RemedyStatus.SETTLED.value:
            return existing
        if existing.razorpay_refund_id:
            result = self.gateway.fetch_refund(existing.razorpay_refund_id)
            applied = self.apply_gateway_status(existing.merchant_id, result)
            return applied or existing
        result = self.gateway.create_refund(
            self.session.get(models.RazorpayPayment, existing.payment_id).razorpay_payment_id,  # type: ignore[union-attr]
            existing.amount_minor,
            existing.idempotency_key,
        )
        existing.razorpay_refund_id = result.razorpay_refund_id
        if result.status == "processed":
            self._settle(existing.merchant_id, existing.idempotency_key, existing)
        else:
            existing.status = self._map_status(result.status)
        self.session.flush()
        return existing

    def _settle(self, merchant_id: str, idempotency_key: str, row: models.RazorpayRefund) -> None:
        self.ledger.settle_if_reserved(merchant_id, idempotency_key)
        row.status = RemedyStatus.SETTLED.value
        self._audit(merchant_id, AuditEventType.REFUND_SETTLED, row, {})
        self.session.flush()

    def _require_captured_payment(
        self,
        merchant_id: str,
        razorpay_payment_id: str,
        amount_minor: int,
    ) -> models.RazorpayPayment:
        payment = self.session.scalar(
            select(models.RazorpayPayment).where(
                models.RazorpayPayment.merchant_id == merchant_id,
                models.RazorpayPayment.razorpay_payment_id == razorpay_payment_id,
            )
        )
        if payment is None:
            raise PaymentNotFound(razorpay_payment_id)
        if payment.status != "captured":
            raise PaymentNotRefundable("payment is not captured")
        if amount_minor > payment.amount_minor:
            raise PaymentNotRefundable("refund exceeds captured payment")
        return payment

    def _save_refund(self, merchant_id, incident_id, payment_pk, amount_minor, idempotency_key, razorpay_refund_id, status):
        row = models.RazorpayRefund(
            id=new_id("rfd"),
            merchant_id=merchant_id,
            incident_id=incident_id,
            payment_id=payment_pk,
            razorpay_refund_id=razorpay_refund_id,
            idempotency_key=idempotency_key,
            amount_minor=amount_minor,
            status=status,
        )
        self.session.add(row)
        self.session.flush()
        return row

    def _refund_by_key(self, merchant_id: str, key: str) -> models.RazorpayRefund | None:
        return self.session.scalar(
            select(models.RazorpayRefund).where(
                models.RazorpayRefund.merchant_id == merchant_id,
                models.RazorpayRefund.idempotency_key == key,
            )
        )

    def _refund_by_razorpay_id(self, razorpay_refund_id: str) -> models.RazorpayRefund | None:
        return self.session.scalar(
            select(models.RazorpayRefund).where(
                models.RazorpayRefund.razorpay_refund_id == razorpay_refund_id
            )
        )

    def _map_status(self, gateway_status: str) -> str:
        if gateway_status == "processed":
            return RemedyStatus.SETTLED.value
        if gateway_status == "failed":
            return RemedyStatus.FAILED.value
        return RemedyStatus.PROCESSING.value

    def _audit(self, merchant_id: str, event_type: AuditEventType, row: models.RazorpayRefund, extra: dict) -> None:
        self.session.add(
            models.AuditEvent(
                id=new_id("aud"),
                merchant_id=merchant_id,
                event_type=event_type.value,
                payload={
                    "refund_id": row.id,
                    "idempotency_key": row.idempotency_key,
                    "razorpay_refund_id": row.razorpay_refund_id,
                    **extra,
                },
            )
        )
