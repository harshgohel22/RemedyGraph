from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.db import models
from app.domain.enums import RemedyStatus
from app.domain.ids import new_id
from app.schemas.incidents import EntitlementPosition
from app.services.entitlement_ledger import (
    EntitlementExists,
    IncidentNotFound,
    InsufficientEntitlement,
    LedgerError,
    ReservationNotActive,
    ReservationRecord,
)
from app.services.exceptions import IdempotencyConflict, MerchantNotFound


class LedgerService:
    """Durable entitlement ledger. Locks the incident row before changing money."""

    def __init__(self, session: Session) -> None:
        self.session = session

    def open_incident(
        self,
        merchant_id: str,
        incident_id: str,
        allowed_entitlement_minor: int,
    ) -> EntitlementPosition:
        if allowed_entitlement_minor < 0:
            raise LedgerError("allowed entitlement must be >= 0")
        merchant = self.session.get(models.Merchant, merchant_id)
        if merchant is None:
            raise MerchantNotFound(merchant_id)
        existing = self.session.get(models.Entitlement, (merchant_id, incident_id))
        if existing is not None:
            raise EntitlementExists(incident_id)
        self.session.add(
            models.Entitlement(
                merchant_id=merchant_id,
                incident_id=incident_id,
                allowed_minor=allowed_entitlement_minor,
                settled_minor=0,
                reserved_minor=0,
                version=1,
            )
        )
        self.session.flush()
        return self.get_position(merchant_id, incident_id)

    def get_position(self, merchant_id: str, incident_id: str) -> EntitlementPosition:
        row = self.session.get(models.Entitlement, (merchant_id, incident_id))
        if row is None:
            raise IncidentNotFound(incident_id)
        return EntitlementPosition(
            incident_id=row.incident_id,
            allowed_entitlement_minor=row.allowed_minor,
            settled_entitlement_minor=row.settled_minor,
            reserved_entitlement_minor=row.reserved_minor,
        )

    def reserve(
        self,
        merchant_id: str,
        incident_id: str,
        amount_minor: int,
        idempotency_key: str,
        remedy_request_id: str | None = None,
    ) -> ReservationRecord:
        if amount_minor < 0:
            raise LedgerError("reservation amount must be integer paise >= 0")
        existing = self._reservation_by_key(merchant_id, idempotency_key)
        if existing is not None:
            if existing.incident_id == incident_id and existing.amount_minor == amount_minor:
                return self._to_record(existing)
            raise IdempotencyConflict(idempotency_key)

        self._lock_entitlement(merchant_id, incident_id)
        result = self.session.execute(
            update(models.Entitlement)
            .where(
                models.Entitlement.merchant_id == merchant_id,
                models.Entitlement.incident_id == incident_id,
                models.Entitlement.settled_minor + models.Entitlement.reserved_minor + amount_minor
                <= models.Entitlement.allowed_minor,
            )
            .values(
                reserved_minor=models.Entitlement.reserved_minor + amount_minor,
                version=models.Entitlement.version + 1,
            )
        )
        if result.rowcount != 1:
            replay = self._reservation_by_key(merchant_id, idempotency_key)
            if replay is not None and replay.incident_id == incident_id and replay.amount_minor == amount_minor:
                return self._to_record(replay)
            position = self.get_position(merchant_id, incident_id)
            raise InsufficientEntitlement(
                f"cannot reserve {amount_minor}; remaining is {position.remaining_minor()}"
            )

        row = models.RemedyReservation(
            id=new_id("rsv"),
            merchant_id=merchant_id,
            incident_id=incident_id,
            remedy_request_id=remedy_request_id or new_id("rrq"),
            idempotency_key=idempotency_key,
            amount_minor=amount_minor,
            status=RemedyStatus.RESERVED.value,
        )
        self.session.add(row)
        self.session.flush()
        return self._to_record(row)

    def get_reservation(self, merchant_id: str, idempotency_key: str) -> ReservationRecord | None:
        row = self._reservation_by_key(merchant_id, idempotency_key)
        if row is None:
            return None
        return self._to_record(row)

    def settle_if_reserved(self, merchant_id: str, idempotency_key: str) -> ReservationRecord:
        row = self._reservation_by_key(merchant_id, idempotency_key)
        if row is None:
            raise ReservationNotActive(idempotency_key)
        if row.status == RemedyStatus.SETTLED.value:
            return self._to_record(row)
        return self.settle(merchant_id, idempotency_key)

    def settle(self, merchant_id: str, idempotency_key: str) -> ReservationRecord:
        row = self._require_reserved(merchant_id, idempotency_key)
        entitlement = self._lock_entitlement(merchant_id, row.incident_id)
        entitlement.reserved_minor -= row.amount_minor
        entitlement.settled_minor += row.amount_minor
        entitlement.version += 1
        row.status = RemedyStatus.SETTLED.value
        self.session.flush()
        return self._to_record(row)

    def release(self, merchant_id: str, idempotency_key: str) -> ReservationRecord:
        return self._drop(merchant_id, idempotency_key, RemedyStatus.RELEASED)

    def fail(self, merchant_id: str, idempotency_key: str) -> ReservationRecord:
        return self._drop(merchant_id, idempotency_key, RemedyStatus.FAILED)

    def _drop(self, merchant_id: str, idempotency_key: str, status: RemedyStatus) -> ReservationRecord:
        row = self._require_reserved(merchant_id, idempotency_key)
        entitlement = self._lock_entitlement(merchant_id, row.incident_id)
        entitlement.reserved_minor -= row.amount_minor
        entitlement.version += 1
        row.status = status.value
        self.session.flush()
        return self._to_record(row)

    def _lock_entitlement(self, merchant_id: str, incident_id: str) -> models.Entitlement:
        row = self.session.execute(
            select(models.Entitlement)
            .where(
                models.Entitlement.merchant_id == merchant_id,
                models.Entitlement.incident_id == incident_id,
            )
            .with_for_update()
        ).scalar_one_or_none()
        if row is None:
            raise IncidentNotFound(incident_id)
        return row

    def _reservation_by_key(self, merchant_id: str, idempotency_key: str) -> models.RemedyReservation | None:
        return self.session.scalar(
            select(models.RemedyReservation).where(
                models.RemedyReservation.merchant_id == merchant_id,
                models.RemedyReservation.idempotency_key == idempotency_key,
            )
        )

    def _require_reserved(self, merchant_id: str, idempotency_key: str) -> models.RemedyReservation:
        row = self._reservation_by_key(merchant_id, idempotency_key)
        if row is None or row.status != RemedyStatus.RESERVED.value:
            raise ReservationNotActive(idempotency_key)
        return row

    def _to_record(self, row: models.RemedyReservation) -> ReservationRecord:
        return ReservationRecord(
            incident_id=row.incident_id,
            remedy_request_id=row.remedy_request_id,
            idempotency_key=row.idempotency_key,
            amount_minor=row.amount_minor,
            status=RemedyStatus(row.status),
        )
