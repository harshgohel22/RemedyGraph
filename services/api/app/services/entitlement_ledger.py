from dataclasses import dataclass

from app.domain.enums import RemedyStatus
from app.domain.ids import new_id
from app.schemas.incidents import EntitlementPosition
from app.services.exceptions import IdempotencyConflict


class LedgerError(ValueError):
    pass


class IncidentNotFound(LedgerError):
    pass


class InsufficientEntitlement(LedgerError):
    pass


class ReservationNotActive(LedgerError):
    pass


class EntitlementExists(LedgerError):
    pass


@dataclass
class ReservationRecord:
    incident_id: str
    remedy_request_id: str
    idempotency_key: str
    amount_minor: int
    status: RemedyStatus


class InMemoryEntitlementLedger:
    """Tracks allowed / settled / reserved per incident. Not Postgres yet — sequential truth only."""

    def __init__(self) -> None:
        self._allowed: dict[str, int] = {}
        self._settled: dict[str, int] = {}
        self._reserved: dict[str, int] = {}
        self._by_key: dict[str, ReservationRecord] = {}

    def open_incident(self, incident_id: str, allowed_entitlement_minor: int) -> EntitlementPosition:
        if allowed_entitlement_minor < 0:
            raise LedgerError("allowed entitlement must be >= 0")
        self._allowed[incident_id] = allowed_entitlement_minor
        self._settled[incident_id] = 0
        self._reserved[incident_id] = 0
        return self.get_position(incident_id)

    def get_position(self, incident_id: str) -> EntitlementPosition:
        if incident_id not in self._allowed:
            raise IncidentNotFound(incident_id)
        position = EntitlementPosition(
            incident_id=incident_id,
            allowed_entitlement_minor=self._allowed[incident_id],
            settled_entitlement_minor=self._settled[incident_id],
            reserved_entitlement_minor=self._reserved[incident_id],
        )
        self._assert_invariant(position)
        return position

    def reserve(
        self,
        incident_id: str,
        amount_minor: int,
        idempotency_key: str,
        remedy_request_id: str | None = None,
    ) -> ReservationRecord:
        if amount_minor < 0:
            raise LedgerError("reservation amount must be integer paise >= 0")
        existing = self._by_key.get(idempotency_key)
        if existing is not None:
            same = (
                existing.incident_id == incident_id
                and existing.amount_minor == amount_minor
            )
            if not same:
                raise IdempotencyConflict(idempotency_key)
            return existing

        position = self.get_position(incident_id)
        remaining = position.remaining_minor()
        if amount_minor > remaining:
            raise InsufficientEntitlement(
                f"cannot reserve {amount_minor}; remaining is {remaining}"
            )

        record = ReservationRecord(
            incident_id=incident_id,
            remedy_request_id=remedy_request_id or new_id("rrq"),
            idempotency_key=idempotency_key,
            amount_minor=amount_minor,
            status=RemedyStatus.RESERVED,
        )
        self._reserved[incident_id] += amount_minor
        self._by_key[idempotency_key] = record
        self._assert_invariant(self.get_position(incident_id))
        return record

    def settle(self, idempotency_key: str) -> ReservationRecord:
        record = self._require_reserved(idempotency_key)
        self._reserved[record.incident_id] -= record.amount_minor
        self._settled[record.incident_id] += record.amount_minor
        record.status = RemedyStatus.SETTLED
        self._assert_invariant(self.get_position(record.incident_id))
        return record

    def release(self, idempotency_key: str) -> ReservationRecord:
        return self._drop_reservation(idempotency_key, RemedyStatus.RELEASED)

    def fail(self, idempotency_key: str) -> ReservationRecord:
        """A failed refund must not keep consuming entitlement (retry can proceed)."""
        return self._drop_reservation(idempotency_key, RemedyStatus.FAILED)

    def _drop_reservation(self, idempotency_key: str, status: RemedyStatus) -> ReservationRecord:
        record = self._require_reserved(idempotency_key)
        self._reserved[record.incident_id] -= record.amount_minor
        record.status = status
        self._assert_invariant(self.get_position(record.incident_id))
        return record

    def _require_reserved(self, idempotency_key: str) -> ReservationRecord:
        record = self._by_key.get(idempotency_key)
        if record is None or record.status is not RemedyStatus.RESERVED:
            raise ReservationNotActive(idempotency_key)
        return record

    def _assert_invariant(self, position: EntitlementPosition) -> None:
        if position.remaining_minor() < 0:
            raise LedgerError("settled + reserved would exceed allowed entitlement")
        if position.settled_entitlement_minor < 0 or position.reserved_entitlement_minor < 0:
            raise LedgerError("settled and reserved must be >= 0")
