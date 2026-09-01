from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import models
from app.domain.enums import AuditEventType, Channel
from app.domain.ids import new_id
from app.schemas.claims import CompiledClaim, CompileClaimResponse
from app.services.claim_extractor import ClaimExtractor, ExtractRequest
from app.services.claim_grounding import IdCatalog, ground_draft
from app.services.exceptions import ClaimNotFound, SupportMessageNotFound


class ClaimCompiler:
    def __init__(self, session: Session, extractor: ClaimExtractor) -> None:
        self.session = session
        self.extractor = extractor

    def compile_message(self, support_message_id: str) -> CompileClaimResponse:
        existing = self.session.scalar(
            select(models.CompiledClaimRecord).where(
                models.CompiledClaimRecord.support_message_id == support_message_id
            )
        )
        if existing is not None:
            return CompileClaimResponse(
                claim=CompiledClaim.model_validate(existing.payload),
                replayed=True,
                audit_id=self._audit(
                    existing,
                    AuditEventType.CLAIM_REPLAYED,
                    {"support_message_id": support_message_id},
                ),
            )

        message = self.session.get(models.SupportMessage, support_message_id)
        if message is None:
            raise SupportMessageNotFound(support_message_id)

        catalog = self._catalog(message.merchant_id, message.customer_id)
        draft = self.extractor.extract(
            ExtractRequest(
                customer_id=message.customer_id,
                channel=Channel(message.channel),
                body=message.body,
                occurred_at=message.occurred_at,
                ingest_order_reference=message.order_reference,
            )
        )
        claim = ground_draft(
            claim_id=new_id("clm"),
            customer_id=message.customer_id,
            channel=Channel(message.channel),
            body=message.body,
            ingest_order_reference=message.order_reference,
            draft=draft,
            catalog=catalog,
        )
        row = models.CompiledClaimRecord(
            id=claim.claim_id,
            merchant_id=message.merchant_id,
            support_message_id=message.id,
            customer_id=message.customer_id,
            payload=claim.model_dump(mode="json"),
        )
        self.session.add(row)
        self.session.flush()
        audit_id = self._audit(
            row,
            AuditEventType.CLAIM_COMPILED,
            {
                "support_message_id": message.id,
                "unknown_fields": claim.unknown_fields,
                "order_reference": claim.order_reference,
            },
        )
        return CompileClaimResponse(claim=claim, replayed=False, audit_id=audit_id)

    def get_claim(self, claim_id: str) -> CompiledClaim:
        row = self.session.get(models.CompiledClaimRecord, claim_id)
        if row is None:
            raise ClaimNotFound(claim_id)
        return CompiledClaim.model_validate(row.payload)

    def _catalog(self, merchant_id: str, customer_id: str) -> IdCatalog:
        orders = self.session.scalars(
            select(models.Order).where(
                models.Order.merchant_id == merchant_id,
                models.Order.customer_id == customer_id,
            )
        ).all()
        order_ids = {order.id for order in orders}
        product_ids: set[str] = set()
        unit_ids: set[str] = set()
        for order in orders:
            for line in order.lines:
                product_ids.add(line.product_id)
                for unit in line.units:
                    unit_ids.add(unit.id)
        return IdCatalog(
            order_ids=frozenset(order_ids),
            product_ids=frozenset(product_ids),
            unit_ids=frozenset(unit_ids),
        )

    def _audit(
        self,
        row: models.CompiledClaimRecord,
        event_type: AuditEventType,
        payload: dict,
    ) -> str:
        audit_id = new_id("aud")
        self.session.add(
            models.AuditEvent(
                id=audit_id,
                merchant_id=row.merchant_id,
                event_type=event_type.value,
                support_message_id=row.support_message_id,
                payload=payload,
            )
        )
        self.session.flush()
        return audit_id
