from datetime import datetime, timezone

from fastapi.testclient import TestClient


def test_audit_lists_world_and_attempt_events(client: TestClient, world_earbuds: dict) -> None:
    assert client.post("/v1/ingest/world", json=world_earbuds).status_code == 200
    ingested = client.post(
        "/v1/ingest/attempts",
        json={
            "message": {
                "merchant_id": "mch_aurum",
                "customer_id": "cus_asha",
                "channel": "EMAIL",
                "body": "The right side produces no audio. Please refund me.",
                "occurred_at": datetime(2026, 8, 20, 9, 0, tzinfo=timezone.utc).isoformat(),
                "external_message_id": "email_audit_1",
            },
            "proposal": {
                "remedy_type": "CASH_REFUND",
                "amount_minor": 499900,
                "entitlement_consumption_minor": 499900,
                "currency": "INR",
                "idempotency_key": "remedy_audit_email_v1",
            },
        },
    )
    assert ingested.status_code == 200
    response = client.get("/v1/audit", params={"merchant_id": "mch_aurum"})
    assert response.status_code == 200
    types = [event["event_type"] for event in response.json()["events"]]
    assert "WORLD_INGESTED" in types
    assert "ATTEMPT_INGESTED" in types


def test_audit_unknown_merchant_is_404(client: TestClient) -> None:
    response = client.get("/v1/audit", params={"merchant_id": "mch_missing"})
    assert response.status_code == 404
