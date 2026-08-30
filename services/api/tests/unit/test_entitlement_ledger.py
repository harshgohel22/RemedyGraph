import pytest

from app.domain.enums import RemedyStatus
from app.services.entitlement_ledger import (
    InMemoryEntitlementLedger,
    InsufficientEntitlement,
    ReservationNotActive,
)
from app.services.exceptions import IdempotencyConflict


def test_reserve_then_settle_consumes_entitlement() -> None:
    ledger = InMemoryEntitlementLedger()
    ledger.open_incident("inc_1", 499900)
    ledger.reserve("inc_1", 499900, "remedy_rrq_001_v1")
    assert ledger.get_position("inc_1").remaining_minor() == 0
    ledger.settle("remedy_rrq_001_v1")
    position = ledger.get_position("inc_1")
    assert position.settled_entitlement_minor == 499900
    assert position.reserved_entitlement_minor == 0
    assert position.remaining_minor() == 0


def test_reserved_blocks_a_second_reservation() -> None:
    ledger = InMemoryEntitlementLedger()
    ledger.open_incident("inc_1", 499900)
    ledger.reserve("inc_1", 499900, "agent_a_key_01")
    with pytest.raises(InsufficientEntitlement):
        ledger.reserve("inc_1", 499900, "agent_b_key_01")


def test_failed_reservation_does_not_keep_consuming() -> None:
    ledger = InMemoryEntitlementLedger()
    ledger.open_incident("inc_1", 499900)
    ledger.reserve("inc_1", 499900, "remedy_fail_v1")
    record = ledger.fail("remedy_fail_v1")
    assert record.status is RemedyStatus.FAILED
    assert ledger.get_position("inc_1").remaining_minor() == 499900
    retry = ledger.reserve("inc_1", 499900, "remedy_retry_v1")
    assert retry.status is RemedyStatus.RESERVED


def test_released_reservation_restores_remaining() -> None:
    ledger = InMemoryEntitlementLedger()
    ledger.open_incident("inc_1", 499900)
    ledger.reserve("inc_1", 200000, "remedy_rel_v1")
    ledger.release("remedy_rel_v1")
    assert ledger.get_position("inc_1").remaining_minor() == 499900


def test_idempotent_reserve_does_not_double_count() -> None:
    ledger = InMemoryEntitlementLedger()
    ledger.open_incident("inc_1", 499900)
    first = ledger.reserve("inc_1", 499900, "remedy_same_key_v1")
    second = ledger.reserve("inc_1", 499900, "remedy_same_key_v1")
    assert first.remedy_request_id == second.remedy_request_id
    assert ledger.get_position("inc_1").reserved_entitlement_minor == 499900


def test_idempotency_conflict_when_key_reused_with_different_amount() -> None:
    ledger = InMemoryEntitlementLedger()
    ledger.open_incident("inc_1", 499900)
    ledger.reserve("inc_1", 200000, "remedy_same_key_v1")
    with pytest.raises(IdempotencyConflict):
        ledger.reserve("inc_1", 300000, "remedy_same_key_v1")


def test_cannot_settle_after_release() -> None:
    ledger = InMemoryEntitlementLedger()
    ledger.open_incident("inc_1", 499900)
    ledger.reserve("inc_1", 499900, "remedy_x_v1")
    ledger.release("remedy_x_v1")
    with pytest.raises(ReservationNotActive):
        ledger.settle("remedy_x_v1")
