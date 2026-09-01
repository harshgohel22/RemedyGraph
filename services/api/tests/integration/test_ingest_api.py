from datetime import datetime, timezone

from fastapi.testclient import TestClient


def _attempt(
    *,
    order_reference: str | None = None,
    amount_minor: object = 499900,
    idempotency_key: str = "remedy_email_refund_v1",
    body: str = "The right side produces no audio. Please refund me.",
    external_message_id: str | None = "email_2001",
) -> dict:
    return {
        "message": {
            "merchant_id": "mch_aurum",
            "customer_id": "cus_asha",
            "channel": "EMAIL",
            "body": body,
            "occurred_at": datetime(2026, 8, 20, 9, 0, tzinfo=timezone.utc).isoformat(),
            "order_reference": order_reference,
            "external_message_id": external_message_id,
        },
        "proposal": {
            "remedy_type": "CASH_REFUND",
            "amount_minor": amount_minor,
            "entitlement_consumption_minor": amount_minor if isinstance(amount_minor, int) else 499900,
            "currency": "INR",
            "idempotency_key": idempotency_key,
        },
    }


def test_health(client: TestClient) -> None:
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_attempt_without_world_is_not_found(client: TestClient) -> None:
    response = client.post("/v1/ingest/attempts", json=_attempt())
    assert response.status_code == 404
    assert "merchant not found" in response.json()["detail"]


def test_world_ingest_stores_lineage(client: TestClient, world_earbuds: dict) -> None:
    response = client.post("/v1/ingest/world", json=world_earbuds)
    assert response.status_code == 200
    body = response.json()
    assert body["merchant_id"] == "mch_aurum"
    assert body["customer_count"] == 1
    assert body["order_count"] == 1
    assert body["unit_count"] == 3
    assert body["support_message_count"] == 1
    assert body["historical_remedy_count"] == 1
    assert body["payment_count"] == 1
    assert body["replaced"] is False
    assert body["audit_id"].startswith("aud_")


def test_ingest_keeps_missing_order_reference_null(
    client: TestClient, world_earbuds: dict
) -> None:
    client.post("/v1/ingest/world", json=world_earbuds)
    response = client.post("/v1/ingest/attempts", json=_attempt(order_reference=None))
    assert response.status_code == 200
    created = response.json()
    assert created["status"] == "PROPOSED"
    assert created["order_reference"] is None
    assert created["incident_id"] is None
    assert created["replayed"] is False

    stored = client.get(f"/v1/ingest/attempts/{created['remedy_request_id']}")
    assert stored.status_code == 200
    payload = stored.json()
    assert payload["order_reference"] is None
    assert payload["incident_id"] is None
    assert payload["body"] == "The right side produces no audio. Please refund me."
    assert payload["amount_minor"] == 499900
    assert payload["status"] == "PROPOSED"


def test_ingest_does_not_correct_wrong_order_reference(
    client: TestClient, world_earbuds: dict
) -> None:
    client.post("/v1/ingest/world", json=world_earbuds)
    response = client.post("/v1/ingest/attempts", json=_attempt(order_reference="ord_does_not_exist"))
    assert response.status_code == 200
    assert response.json()["order_reference"] == "ord_does_not_exist"

    stored = client.get(f"/v1/ingest/attempts/{response.json()['remedy_request_id']}")
    assert stored.json()["order_reference"] == "ord_does_not_exist"


def test_float_amount_is_rejected(client: TestClient, world_earbuds: dict) -> None:
    client.post("/v1/ingest/world", json=world_earbuds)
    response = client.post("/v1/ingest/attempts", json=_attempt(amount_minor=4999.50))
    assert response.status_code == 422


def test_idempotent_replay_does_not_create_a_second_request(
    client: TestClient, world_earbuds: dict
) -> None:
    client.post("/v1/ingest/world", json=world_earbuds)
    first = client.post("/v1/ingest/attempts", json=_attempt())
    second = client.post("/v1/ingest/attempts", json=_attempt())
    assert first.status_code == 200
    assert second.status_code == 200
    assert second.json()["replayed"] is True
    assert second.json()["remedy_request_id"] == first.json()["remedy_request_id"]
    assert second.json()["support_message_id"] == first.json()["support_message_id"]


def test_idempotency_conflict_when_payload_differs(
    client: TestClient, world_earbuds: dict
) -> None:
    client.post("/v1/ingest/world", json=world_earbuds)
    first = client.post("/v1/ingest/attempts", json=_attempt())
    assert first.status_code == 200
    conflict = client.post(
        "/v1/ingest/attempts",
        json=_attempt(body="Different text, same key."),
    )
    assert conflict.status_code == 409


def test_unknown_customer_is_rejected(client: TestClient, world_earbuds: dict) -> None:
    client.post("/v1/ingest/world", json=world_earbuds)
    payload = _attempt()
    payload["message"]["customer_id"] = "cus_unknown"
    response = client.post("/v1/ingest/attempts", json=payload)
    assert response.status_code == 404
