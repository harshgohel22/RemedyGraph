from fastapi.testclient import TestClient

from app.domain.enums import Decision, ReasonCode


def test_demo_lists_three_pitch_scenarios(client: TestClient) -> None:
    response = client.get("/v1/demo/scenarios")
    assert response.status_code == 200
    ids = [row["scenario_id"] for row in response.json()]
    assert ids == ["allow", "review", "prevent"]


def test_demo_allow_executes_refund(client: TestClient) -> None:
    response = client.post("/v1/demo/run", json={"scenario_id": "allow"})
    assert response.status_code == 200
    body = response.json()
    assert body["execution"]["evaluation"]["decision"]["decision"] == Decision.ALLOW.value
    assert body["execution"]["executed"] is True
    assert body["execution"]["refund"]["status"] == "SETTLED"


def test_demo_review_does_not_guess_unit(client: TestClient) -> None:
    response = client.post("/v1/demo/run", json={"scenario_id": "review"})
    assert response.status_code == 200
    body = response.json()
    decision = body["execution"]["evaluation"]["decision"]
    assert decision["decision"] == Decision.REVIEW.value
    assert ReasonCode.UNIT_AMBIGUOUS.value in decision["reason_codes"]
    assert body["execution"]["executed"] is False


def test_demo_prevent_blocks_email_after_whatsapp(client: TestClient) -> None:
    response = client.post("/v1/demo/run", json={"scenario_id": "prevent"})
    assert response.status_code == 200
    body = response.json()
    assert body["execution"]["evaluation"]["decision"]["decision"] == Decision.PREVENT_DUPLICATE.value
    assert body["execution"]["executed"] is False
    assert body["execution"]["evaluation"]["decision"]["avoidable_overcompensation_minor"] == 499900


def test_demo_scenarios_run_back_to_back_on_one_database(client: TestClient) -> None:
    """Pitch clicks Prevent then Allow then Review against the same SQLite file."""

    expected = {
        "prevent": Decision.PREVENT_DUPLICATE.value,
        "allow": Decision.ALLOW.value,
        "review": Decision.REVIEW.value,
    }
    for scenario_id, decision in expected.items():
        response = client.post("/v1/demo/run", json={"scenario_id": scenario_id})
        assert response.status_code == 200, response.text
        assert response.json()["execution"]["evaluation"]["decision"]["decision"] == decision

    again = client.post("/v1/demo/run", json={"scenario_id": "allow"})
    assert again.status_code == 200, again.text
    assert again.json()["execution"]["evaluation"]["decision"]["decision"] == Decision.ALLOW.value

