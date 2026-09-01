import json

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db import models
from app.domain.enums import AuditEventType
from app.domain.ids import new_id
from app.services.exceptions import InvalidWebhookSignature
from app.services.razorpay_client import RefundResult
from app.services.refund_executor import RefundExecutor
from app.services.webhook_signature import verify_webhook_signature


class WebhookProcessor:
    def __init__(self, session: Session, executor: RefundExecutor) -> None:
        self.session = session
        self.executor = executor

    def handle(self, raw_body: bytes, signature: str, event_id: str) -> dict:
        if not verify_webhook_signature(raw_body, signature, settings.razorpay_webhook_secret):
            raise InvalidWebhookSignature()
        if not event_id:
            event_id = "missing-event-id"
        existing = self.session.get(models.WebhookEvent, event_id)
        if existing is not None:
            return {"accepted": True, "duplicate": True}

        payload = json.loads(raw_body.decode("utf-8"))
        event_type = str(payload.get("event", "unknown"))
        entity = payload.get("payload", {}).get("refund", {}).get("entity", {})
        razorpay_refund_id = str(entity.get("id") or "")
        refund_row = self._refund_row(razorpay_refund_id)
        merchant_id = refund_row.merchant_id if refund_row is not None else None

        self.session.add(
            models.WebhookEvent(
                event_id=event_id,
                merchant_id=merchant_id,
                event_type=event_type,
                payload=payload,
            )
        )
        if merchant_id:
            self.session.add(
                models.AuditEvent(
                    id=new_id("aud"),
                    merchant_id=merchant_id,
                    event_type=AuditEventType.WEBHOOK_RECEIVED.value,
                    payload={"event_id": event_id, "event_type": event_type},
                )
            )
        self.session.flush()

        if event_type in {"refund.processed", "refund.failed"} and razorpay_refund_id:
            result = RefundResult(
                razorpay_refund_id=razorpay_refund_id,
                payment_id=str(entity.get("payment_id", "")),
                amount_minor=int(entity.get("amount") or 0),
                status="processed" if event_type == "refund.processed" else "failed",
                idempotency_key="",
            )
            self.executor.apply_gateway_status(merchant_id or "", result)
        return {"accepted": True, "duplicate": False}

    def _refund_row(self, razorpay_refund_id: str) -> models.RazorpayRefund | None:
        if not razorpay_refund_id:
            return None
        return self.session.scalar(
            select(models.RazorpayRefund).where(
                models.RazorpayRefund.razorpay_refund_id == razorpay_refund_id
            )
        )
