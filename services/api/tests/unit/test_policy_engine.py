import json
from pathlib import Path

import pytest

from app.domain.enums import Decision, IncidentRelation, ReasonCode
from app.evaluation.scenario_schema import SeedScenarioFile
from app.schemas.incidents import EntitlementPosition
from app.services.policy_engine import PolicyInvariantError, decide

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "seed_scenarios.json"


def _scenarios() -> SeedScenarioFile:
    return SeedScenarioFile.model_validate(json.loads(FIXTURES.read_text()))


def test_seed_file_has_twelve_scenarios() -> None:
    assert len(_scenarios().scenarios) == 12


@pytest.mark.parametrize("scenario", _scenarios().scenarios, ids=lambda s: s.scenario_id)
def test_policy_matches_seed_expected(scenario) -> None:
    position = EntitlementPosition(
        incident_id=scenario.incident_id,
        allowed_entitlement_minor=scenario.allowed_entitlement_minor,
        settled_entitlement_minor=scenario.settled_entitlement_minor,
        reserved_entitlement_minor=scenario.reserved_entitlement_minor,
    )
    result = decide(
        position,
        scenario.relation,
        scenario.proposed_consumption_minor,
        requires_review=scenario.requires_review,
        contradictory_fields=scenario.contradictory_fields,
    )
    exp = scenario.expected
    assert result.decision is exp.decision
    assert result.remaining_before_minor == exp.remaining_before_minor
    assert result.remaining_after_minor == exp.remaining_after_minor
    assert result.avoidable_overcompensation_minor == exp.avoidable_overcompensation_minor
    assert result.max_safe_amount_minor == exp.max_safe_amount_minor
    assert isinstance(result.allowed_entitlement_minor, int)
    assert isinstance(result.proposed_consumption_minor, int)


def test_review_does_not_consume_remaining() -> None:
    position = EntitlementPosition(
        incident_id="inc_x",
        allowed_entitlement_minor=499900,
        settled_entitlement_minor=0,
        reserved_entitlement_minor=0,
    )
    result = decide(position, IncidentRelation.UNCERTAIN, 499900)
    assert result.decision is Decision.REVIEW
    assert result.remaining_after_minor == result.remaining_before_minor


def test_contradiction_forces_review_even_if_same_incident() -> None:

    position = EntitlementPosition(
        incident_id="inc_c",
        allowed_entitlement_minor=499900,
        settled_entitlement_minor=0,
        reserved_entitlement_minor=0,
    )
    result = decide(
        position,
        IncidentRelation.SAME_INCIDENT,
        499900,
        contradictory_fields=["order_reference"],
    )
    assert result.decision is Decision.REVIEW
    assert ReasonCode.CONTRADICTION in result.reason_codes


def test_inconsistent_ledger_is_rejected() -> None:

    position = EntitlementPosition(
        incident_id="inc_bad",
        allowed_entitlement_minor=100,
        settled_entitlement_minor=80,
        reserved_entitlement_minor=40,
    )
    with pytest.raises(PolicyInvariantError):
        decide(position, IncidentRelation.SAME_INCIDENT, 10)


def test_naive_remaining_that_ignores_reserved_would_allow_a_double_spend() -> None:
    """Naive: remaining = allowed - settled. That would ALLOW a second ₹4,999 while one is reserved."""
    allowed = 499900
    settled = 0
    reserved = 499900
    proposed = 499900
    naive_remaining = allowed - settled
    correct_remaining = allowed - settled - reserved
    assert naive_remaining == 499900
    assert correct_remaining == 0
    result = decide(
        EntitlementPosition(
            incident_id="inc_naive",
            allowed_entitlement_minor=allowed,
            settled_entitlement_minor=settled,
            reserved_entitlement_minor=reserved,
        ),
        IncidentRelation.SAME_INCIDENT,
        proposed,
    )
    assert result.decision is Decision.PREVENT_DUPLICATE
    assert ReasonCode.RESERVATION_HELD in result.reason_codes
