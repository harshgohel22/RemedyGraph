from copy import deepcopy
from datetime import datetime, timezone

from fastapi.testclient import TestClient

from app.api.deps import get_incident_linker
from app.domain.enums import IncidentRelation
from app.schemas.incidents import LinkDraft
from app.services.incident_linker import FakeIncidentLinker


def _email_attempt() -> dict:
    return {
        "message": {
            "merchant_id": "mch_aurum",
            "customer_id": "cus_asha",
            "channel": "EMAIL",
            "body": "The right side produces no audio. Please refund me.",
            "occurred_at": datetime(2026, 8, 20, 9, 0, tzinfo=timezone.utc).isoformat(),
            "order_reference": None,
            "external_message_id": "email_2001",
        },
        "proposal": {
            "remedy_type": "CASH_REFUND",
            "amount_minor": 499900,
            "entitlement_consumption_minor": 499900,
            "currency": "INR",
            "idempotency_key": "remedy_email_refund_v1",
        },
    }


def _compile_email(client: TestClient, world: dict) -> str:
    client.post("/v1/ingest/world", json=world)
    ingested = client.post("/v1/ingest/attempts", json=_email_attempt())
    compiled = client.post(
        "/v1/claims/compile",
        json={"support_message_id": ingested.json()["support_message_id"]},
    )
    assert compiled.status_code == 200
    return compiled.json()["claim"]["claim_id"]


def test_email_links_as_same_as_whatsapp_replacement(
    client: TestClient, world_earbuds: dict
) -> None:
    claim_id = _compile_email(client, world_earbuds)
    response = client.post(f"/v1/claims/{claim_id}/link")
    assert response.status_code == 200
    body = response.json()
    assert body["replayed"] is False
    primary = body["primary"]
    assert primary["relation"] == IncidentRelation.SAME_INCIDENT.value
    assert primary["candidate_incident_id"] == "inc_msg_wa_001"
    assert primary["requires_review"] is False
    assert primary["claim_id"] == claim_id

    stored = client.get(f"/v1/claims/{claim_id}/link")
    assert stored.status_code == 200
    assert stored.json()["primary"]["candidate_incident_id"] == "inc_msg_wa_001"


def test_link_is_idempotent(client: TestClient, world_earbuds: dict) -> None:
    claim_id = _compile_email(client, world_earbuds)
    first = client.post(f"/v1/claims/{claim_id}/link")
    second = client.post(f"/v1/claims/{claim_id}/link")
    assert second.status_code == 200
    assert second.json()["replayed"] is True
    assert second.json()["primary"]["candidate_incident_id"] == first.json()["primary"]["candidate_incident_id"]


def test_whatsapp_without_priors_is_new(client: TestClient, world_earbuds: dict) -> None:
    client.post("/v1/ingest/world", json=world_earbuds)
    compiled = client.post("/v1/claims/compile", json={"support_message_id": "msg_wa_001"})
    claim_id = compiled.json()["claim"]["claim_id"]
    response = client.post(f"/v1/claims/{claim_id}/link")
    assert response.status_code == 200
    primary = response.json()["primary"]
    assert primary["relation"] == IncidentRelation.NEW_INCIDENT.value
    assert primary["candidate_incident_id"] == f"inc_{claim_id}"


def test_fake_same_on_unrelated_invoice_is_downgraded(
    client: TestClient, world_earbuds: dict
) -> None:
    world = deepcopy(world_earbuds)
    world["support_messages"] = [
        {
            "support_message_id": "msg_invoice",
            "customer_id": "cus_asha",
            "channel": "EMAIL",
            "body": "Where is the GST invoice for last month?",
            "occurred_at": "2026-07-02T08:00:00+05:30",
            "order_reference": None,
            "external_message_id": "email_invoice",
        }
    ]
    world["historical_remedies"] = []
    claim_id = _compile_email(client, world)
    fake = FakeIncidentLinker(
        LinkDraft(relation=IncidentRelation.SAME_INCIDENT, confidence=0.99, evidence_for=["hallucinated"])
    )
    client.app.dependency_overrides[get_incident_linker] = lambda: fake
    try:
        response = client.post(f"/v1/claims/{claim_id}/link")
    finally:
        client.app.dependency_overrides.pop(get_incident_linker, None)
    assert response.status_code == 200
    assert response.json()["primary"]["relation"] == IncidentRelation.UNCERTAIN.value
    assert response.json()["primary"]["requires_review"] is True
    assert len(fake.calls) == 1


def test_unknown_claim_link_is_not_found(client: TestClient) -> None:
    response = client.post("/v1/claims/clm_missing/link")
    assert response.status_code == 404
