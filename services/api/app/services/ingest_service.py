from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import models
from app.domain.enums import AuditEventType, Channel, Currency, RemedyStatus, RemedyType
from app.domain.ids import new_id
from app.schemas.ingest import IngestAttemptRequest, IngestAttemptResponse, StoredAttempt
from app.schemas.world import WorldIngestRequest, WorldIngestResponse, WorldItemUnitIn
from app.services.exceptions import (
    AttemptNotFound,
    CustomerNotFound,
    IdempotencyConflict,
    MerchantExists,
    MerchantNotFound,
    WorldValidationError,
)


class IngestService:
    def __init__(self, session: Session) -> None:
        self.session = session

    def ingest_world(self, request: WorldIngestRequest) -> WorldIngestResponse:
        existing = self.session.get(models.Merchant, request.merchant_id)
        replaced = False
        if existing is not None:
            if not request.replace:
                raise MerchantExists(request.merchant_id)
            self.session.delete(existing)
            self.session.flush()
            replaced = True

        self._validate_world(request)

        merchant = models.Merchant(id=request.merchant_id, name=request.merchant_name)
        self.session.add(merchant)

        for customer in request.customers:
            self.session.add(
                models.Customer(
                    id=customer.customer_id,
                    merchant_id=request.merchant_id,
                    display_name=customer.display_name,
                )
            )
        self.session.flush()

        unit_count = 0
        for order in request.orders:
            self.session.add(
                models.Order(
                    id=order.order_id,
                    merchant_id=request.merchant_id,
                    customer_id=order.customer_id,
                    created_at=order.created_at,
                )
            )
            self.session.flush()
            for line in order.lines:
                self.session.add(
                    models.OrderLine(
                        id=line.order_line_id,
                        order_id=order.order_id,
                        product_id=line.product_id,
                        product_name=line.product_name,
                        quantity=line.quantity,
                        unit_price_minor=line.unit_price_minor,
                    )
                )
                self.session.flush()
                for unit in self._ordered_units(line.units):
                    self.session.add(
                        models.ItemUnit(
                            id=unit.unit_id,
                            order_line_id=line.order_line_id,
                            product_id=line.product_id,
                            parent_unit_id=unit.parent_unit_id,
                        )
                    )
                    self.session.flush()
                    unit_count += 1

        for message in request.support_messages:
            self.session.add(
                models.SupportMessage(
                    id=message.support_message_id,
                    merchant_id=request.merchant_id,
                    customer_id=message.customer_id,
                    channel=message.channel.value,
                    body=message.body,
                    order_reference=message.order_reference,
                    external_message_id=message.external_message_id,
                    occurred_at=message.occurred_at,
                )
            )
        self.session.flush()

        for remedy in request.historical_remedies:
            self.session.add(
                models.RemedyRequest(
                    id=remedy.remedy_request_id,
                    merchant_id=request.merchant_id,
                    customer_id=remedy.customer_id,
                    support_message_id=remedy.support_message_id,
                    incident_id=None,
                    item_unit_id=remedy.item_unit_id,
                    remedy_type=remedy.remedy_type.value,
                    amount_minor=remedy.amount_minor,
                    entitlement_consumption_minor=remedy.entitlement_consumption_minor,
                    merchant_cost_minor=remedy.merchant_cost_minor,
                    currency=remedy.currency.value,
                    idempotency_key=remedy.idempotency_key,
                    status=remedy.status.value,
                )
            )

        for payment in request.razorpay_payments:
            self.session.add(
                models.RazorpayPayment(
                    id=new_id("pay"),
                    merchant_id=request.merchant_id,
                    internal_order_id=payment.internal_order_id,
                    razorpay_payment_id=payment.razorpay_payment_id,
                    razorpay_order_id=payment.razorpay_order_id,
                    amount_minor=payment.amount_minor,
                    status=payment.status,
                )
            )
        self.session.flush()

        audit_id = new_id("aud")
        self.session.add(
            models.AuditEvent(
                id=audit_id,
                merchant_id=request.merchant_id,
                event_type=AuditEventType.WORLD_INGESTED.value,
                payload={
                    "merchant_id": request.merchant_id,
                    "customer_count": len(request.customers),
                    "order_count": len(request.orders),
                    "unit_count": unit_count,
                    "support_message_count": len(request.support_messages),
                    "historical_remedy_count": len(request.historical_remedies),
                    "payment_count": len(request.razorpay_payments),
                    "replaced": replaced,
                },
            )
        )
        self.session.flush()

        return WorldIngestResponse(
            merchant_id=request.merchant_id,
            customer_count=len(request.customers),
            order_count=len(request.orders),
            unit_count=unit_count,
            support_message_count=len(request.support_messages),
            historical_remedy_count=len(request.historical_remedies),
            payment_count=len(request.razorpay_payments),
            audit_id=audit_id,
            replaced=replaced,
        )

    def ingest_attempt(self, request: IngestAttemptRequest) -> IngestAttemptResponse:
        merchant = self.session.get(models.Merchant, request.message.merchant_id)
        if merchant is None:
            raise MerchantNotFound(request.message.merchant_id)

        customer = self.session.get(models.Customer, request.message.customer_id)
        if customer is None or customer.merchant_id != request.message.merchant_id:
            raise CustomerNotFound(request.message.customer_id)

        existing = self._get_by_idempotency(
            request.message.merchant_id,
            request.proposal.idempotency_key,
        )
        if existing is not None:
            if not self._proposal_matches(existing, request):
                raise IdempotencyConflict(request.proposal.idempotency_key)
            audit_id = self._record_replay(existing)
            return self._attempt_response(existing, audit_id=audit_id, replayed=True)

        message = self._get_or_create_message(request)

        remedy = models.RemedyRequest(
            id=new_id("rrq"),
            merchant_id=request.message.merchant_id,
            customer_id=request.message.customer_id,
            support_message_id=message.id,
            incident_id=None,
            item_unit_id=None,
            remedy_type=request.proposal.remedy_type.value,
            amount_minor=request.proposal.amount_minor,
            entitlement_consumption_minor=request.proposal.entitlement_consumption_minor,
            merchant_cost_minor=request.proposal.merchant_cost_minor,
            currency=request.proposal.currency.value,
            idempotency_key=request.proposal.idempotency_key,
            status=RemedyStatus.PROPOSED.value,
        )
        self.session.add(remedy)
        self.session.flush()

        audit_id = new_id("aud")
        self.session.add(
            models.AuditEvent(
                id=audit_id,
                merchant_id=request.message.merchant_id,
                event_type=AuditEventType.ATTEMPT_INGESTED.value,
                support_message_id=message.id,
                remedy_request_id=remedy.id,
                payload={
                    "channel": request.message.channel.value,
                    "order_reference": request.message.order_reference,
                    "remedy_type": request.proposal.remedy_type.value,
                    "amount_minor": request.proposal.amount_minor,
                    "entitlement_consumption_minor": request.proposal.entitlement_consumption_minor,
                    "idempotency_key": request.proposal.idempotency_key,
                    "incident_id": None,
                },
            )
        )
        self.session.flush()
        return self._attempt_response(remedy, audit_id=audit_id, replayed=False)

    def get_attempt(self, remedy_request_id: str) -> StoredAttempt:
        remedy = self.session.get(models.RemedyRequest, remedy_request_id)
        if remedy is None:
            raise AttemptNotFound(remedy_request_id)
        message = self.session.get(models.SupportMessage, remedy.support_message_id)
        if message is None:
            raise AttemptNotFound(remedy_request_id)
        return StoredAttempt(
            remedy_request_id=remedy.id,
            support_message_id=message.id,
            merchant_id=remedy.merchant_id,
            customer_id=remedy.customer_id,
            channel=Channel(message.channel),
            body=message.body,
            order_reference=message.order_reference,
            remedy_type=RemedyType(remedy.remedy_type),
            amount_minor=remedy.amount_minor,
            entitlement_consumption_minor=remedy.entitlement_consumption_minor,
            merchant_cost_minor=remedy.merchant_cost_minor,
            currency=Currency(remedy.currency),
            idempotency_key=remedy.idempotency_key,
            status=RemedyStatus(remedy.status),
            incident_id=remedy.incident_id,
            occurred_at=message.occurred_at,
        )

    def _get_or_create_message(self, request: IngestAttemptRequest) -> models.SupportMessage:
        if request.message.external_message_id:
            found = self.session.scalar(
                select(models.SupportMessage).where(
                    models.SupportMessage.merchant_id == request.message.merchant_id,
                    models.SupportMessage.external_message_id == request.message.external_message_id,
                )
            )
            if found is not None:
                same_content = (
                    found.customer_id == request.message.customer_id
                    and found.channel == request.message.channel.value
                    and found.body == request.message.body
                    and found.order_reference == request.message.order_reference
                )
                if not same_content:
                    raise IdempotencyConflict(request.message.external_message_id)
                return found

        message = models.SupportMessage(
            id=new_id("msg"),
            merchant_id=request.message.merchant_id,
            customer_id=request.message.customer_id,
            channel=request.message.channel.value,
            body=request.message.body,
            order_reference=request.message.order_reference,
            external_message_id=request.message.external_message_id,
            occurred_at=request.message.occurred_at,
        )
        self.session.add(message)
        self.session.flush()
        return message

    def _get_by_idempotency(self, merchant_id: str, key: str) -> models.RemedyRequest | None:
        return self.session.scalar(
            select(models.RemedyRequest).where(
                models.RemedyRequest.merchant_id == merchant_id,
                models.RemedyRequest.idempotency_key == key,
            )
        )

    def _proposal_matches(self, existing: models.RemedyRequest, request: IngestAttemptRequest) -> bool:
        message = self.session.get(models.SupportMessage, existing.support_message_id)
        if message is None:
            return False
        return (
            existing.customer_id == request.message.customer_id
            and existing.remedy_type == request.proposal.remedy_type.value
            and existing.amount_minor == request.proposal.amount_minor
            and existing.entitlement_consumption_minor == request.proposal.entitlement_consumption_minor
            and existing.currency == request.proposal.currency.value
            and existing.merchant_cost_minor == request.proposal.merchant_cost_minor
            and message.body == request.message.body
            and message.channel == request.message.channel.value
            and message.order_reference == request.message.order_reference
        )

    def _record_replay(self, existing: models.RemedyRequest) -> str:
        audit_id = new_id("aud")
        self.session.add(
            models.AuditEvent(
                id=audit_id,
                merchant_id=existing.merchant_id,
                event_type=AuditEventType.ATTEMPT_REPLAYED.value,
                support_message_id=existing.support_message_id,
                remedy_request_id=existing.id,
                payload={"idempotency_key": existing.idempotency_key},
            )
        )
        self.session.flush()
        return audit_id

    def _attempt_response(
        self,
        remedy: models.RemedyRequest,
        *,
        audit_id: str,
        replayed: bool,
    ) -> IngestAttemptResponse:
        message = self.session.get(models.SupportMessage, remedy.support_message_id)
        return IngestAttemptResponse(
            support_message_id=remedy.support_message_id,
            remedy_request_id=remedy.id,
            audit_id=audit_id,
            status=RemedyStatus(remedy.status),
            order_reference=message.order_reference if message else None,
            incident_id=remedy.incident_id,
            replayed=replayed,
        )

    def _validate_world(self, request: WorldIngestRequest) -> None:
        customer_ids = {c.customer_id for c in request.customers}
        if len(customer_ids) != len(request.customers):
            raise WorldValidationError("duplicate customer_id in world")

        order_ids: set[str] = set()
        unit_ids: set[str] = set()
        line_ids: set[str] = set()
        for order in request.orders:
            if order.order_id in order_ids:
                raise WorldValidationError(f"duplicate order_id: {order.order_id}")
            order_ids.add(order.order_id)
            if order.customer_id not in customer_ids:
                raise WorldValidationError(f"order {order.order_id} references unknown customer")
            for line in order.lines:
                if line.order_line_id in line_ids:
                    raise WorldValidationError(f"duplicate order_line_id: {line.order_line_id}")
                line_ids.add(line.order_line_id)
                for unit in line.units:
                    if unit.unit_id in unit_ids:
                        raise WorldValidationError(f"duplicate unit_id: {unit.unit_id}")
                    unit_ids.add(unit.unit_id)

        for unit in (u for order in request.orders for line in order.lines for u in line.units):
            if unit.parent_unit_id is not None and unit.parent_unit_id not in unit_ids:
                raise WorldValidationError(f"parent_unit_id not in world: {unit.parent_unit_id}")

        message_ids = {m.support_message_id for m in request.support_messages}
        if len(message_ids) != len(request.support_messages):
            raise WorldValidationError("duplicate support_message_id in world")
        for message in request.support_messages:
            if message.customer_id not in customer_ids:
                raise WorldValidationError(f"support message references unknown customer: {message.customer_id}")

        remedy_ids = {r.remedy_request_id for r in request.historical_remedies}
        if len(remedy_ids) != len(request.historical_remedies):
            raise WorldValidationError("duplicate remedy_request_id in world")
        keys = {r.idempotency_key for r in request.historical_remedies}
        if len(keys) != len(request.historical_remedies):
            raise WorldValidationError("duplicate idempotency_key in world")
        for remedy in request.historical_remedies:
            if remedy.customer_id not in customer_ids:
                raise WorldValidationError(f"historical remedy references unknown customer: {remedy.customer_id}")
            if remedy.support_message_id not in message_ids:
                raise WorldValidationError(
                    f"historical remedy references unknown support message: {remedy.support_message_id}"
                )
            if remedy.item_unit_id is not None and remedy.item_unit_id not in unit_ids:
                raise WorldValidationError(f"historical remedy references unknown unit: {remedy.item_unit_id}")

        payment_ids = {p.razorpay_payment_id for p in request.razorpay_payments}
        if len(payment_ids) != len(request.razorpay_payments):
            raise WorldValidationError("duplicate razorpay_payment_id in world")
        for payment in request.razorpay_payments:
            if payment.internal_order_id is not None and payment.internal_order_id not in order_ids:
                raise WorldValidationError(
                    f"payment references unknown order: {payment.internal_order_id}"
                )

    def _ordered_units(self, units: list[WorldItemUnitIn]) -> list[WorldItemUnitIn]:
        remaining = list(units)
        placed: list[WorldItemUnitIn] = []
        placed_ids: set[str] = set()
        while remaining:
            progress = False
            next_remaining: list[WorldItemUnitIn] = []
            for unit in remaining:
                if unit.parent_unit_id is None or unit.parent_unit_id in placed_ids:
                    placed.append(unit)
                    placed_ids.add(unit.unit_id)
                    progress = True
                else:
                    next_remaining.append(unit)
            if not progress:
                raise WorldValidationError("item unit parent cycle or missing parent in line")
            remaining = next_remaining
        return placed
