import json
from pathlib import Path

from fastapi.testclient import TestClient

from app.domain.enums import Decision

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "seed_scenarios.json"


def test_evaluate_endpoint_allows_new_incident(client: TestClient) -> None:
    payload = json.loads(FIXTURES.read_text())["scenarios"][0]
    response = client.post("/v1/evaluate/scenario", json=payload)
    assert response.status_code == 200
    body = response.json()
    assert body["decision"] == Decision.ALLOW.value
    assert body["remaining_before_minor"] == 499900
    assert body["remaining_after_minor"] == 0
    assert isinstance(body["allowed_entitlement_minor"], int)


def test_evaluate_endpoint_prevents_exhausted_entitlement(client: TestClient) -> None:
    scenarios = json.loads(FIXTURES.read_text())["scenarios"]
    exhausted = next(s for s in scenarios if s["scenario_id"] == "seed_same_incident_exceeds_prevent")
    response = client.post("/v1/evaluate/scenario", json=exhausted)
    assert response.status_code == 200
    assert response.json()["decision"] == Decision.PREVENT_DUPLICATE.value
    assert response.json()["avoidable_overcompensation_minor"] == 499900
