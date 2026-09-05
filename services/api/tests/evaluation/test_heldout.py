import json
from pathlib import Path

import pytest

from fastapi.testclient import TestClient

from app.domain.enums import Decision
from app.evaluation.runner import format_report, load_heldout, run_heldout
from app.evaluation.scenario_schema import SeedScenarioFile
from app.schemas.incidents import EntitlementPosition
from app.services.policy_engine import decide

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"


def test_heldout_catalog_is_frozen_and_has_a_documented_miss() -> None:
    catalog = load_heldout()
    assert catalog.frozen_at == "2026-09-05"
    assert len(catalog.cases) == 16
    misses = [case for case in catalog.cases if case.documented_miss]
    assert len(misses) == 1
    assert misses[0].case_id == "holdout_paraphrase_miss"
    assert misses[0].gold_decision is Decision.PREVENT_DUPLICATE


def test_heldout_end_to_end_metrics_are_honest() -> None:
    report = run_heldout()
    assert report.case_count == 16
    assert report.documented_miss_confirmed is True
    assert report.prevent_precision == 0.625
    assert report.prevent_recall == pytest.approx(5 / 6)
    assert report.same_precision == pytest.approx(2 / 3)
    assert report.same_recall == pytest.approx(6 / 7)
    assert report.decision_accuracy == 0.75
    assert report.false_positive_cost_minor == 1_499_700
    assert report.missed_loss_minor == 0
    text = format_report(report)
    assert "holdout_paraphrase_miss" in text
    assert "FALSE_PREVENT" in text


def test_heldout_policy_scenarios_match_exactly(client: TestClient) -> None:
    payload = SeedScenarioFile.model_validate(json.loads((FIXTURES / "heldout_policy.json").read_text()))
    for scenario in payload.scenarios:
        position = EntitlementPosition(
            incident_id=scenario.incident_id,
            allowed_entitlement_minor=scenario.allowed_entitlement_minor,
            settled_entitlement_minor=scenario.settled_entitlement_minor,
            reserved_entitlement_minor=scenario.reserved_entitlement_minor,
        )
        decision = decide(
            position,
            scenario.relation,
            scenario.proposed_consumption_minor,
            requires_review=scenario.requires_review,
            contradictory_fields=scenario.contradictory_fields,
        )
        assert decision.decision is scenario.expected.decision
        assert decision.remaining_before_minor == scenario.expected.remaining_before_minor
        assert decision.remaining_after_minor == scenario.expected.remaining_after_minor
        assert decision.avoidable_overcompensation_minor == scenario.expected.avoidable_overcompensation_minor
        response = client.post("/v1/evaluate/scenario", json=scenario.model_dump(mode="json"))
        assert response.status_code == 200
        assert response.json()["decision"] == scenario.expected.decision.value
