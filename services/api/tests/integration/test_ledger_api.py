from fastapi.testclient import TestClient

from app.domain.enums import RemedyStatus


def _bootstrap(client: TestClient, world_earbuds: dict) -> None:
    assert client.post("/v1/ingest/world", json=world_earbuds).status_code == 200
    opened = client.post(
        "/v1/ledger/entitlements",
        json={
            "merchant_id": "mch_aurum",
            "incident_id": "inc_right_audio",
            "allowed_entitlement_minor": 499900,
        },
    )
    assert opened.status_code == 200
    assert opened.json()["remaining_minor"] == 499900


def test_open_entitlement_requires_merchant(client: TestClient) -> None:
    response = client.post(
        "/v1/ledger/entitlements",
        json={
            "merchant_id": "mch_missing",
            "incident_id": "inc_1",
            "allowed_entitlement_minor": 499900,
        },
    )
    assert response.status_code == 404


def test_reserve_blocks_second_agent_on_same_incident(
    client: TestClient, world_earbuds: dict
) -> None:
    _bootstrap(client, world_earbuds)
    first = client.post(
        "/v1/ledger/reservations",
        json={
            "merchant_id": "mch_aurum",
            "incident_id": "inc_right_audio",
            "amount_minor": 499900,
            "idempotency_key": "agent_a_reserve_v1",
        },
    )
    assert first.status_code == 200
    assert first.json()["status"] == RemedyStatus.RESERVED.value

    second = client.post(
        "/v1/ledger/reservations",
        json={
            "merchant_id": "mch_aurum",
            "incident_id": "inc_right_audio",
            "amount_minor": 499900,
            "idempotency_key": "agent_b_reserve_v1",
        },
    )
    assert second.status_code == 409

    position = client.get(
        "/v1/ledger/entitlements/inc_right_audio",
        params={"merchant_id": "mch_aurum"},
    )
    assert position.json()["reserved_entitlement_minor"] == 499900
    assert position.json()["remaining_minor"] == 0


def test_failed_reservation_allows_retry(client: TestClient, world_earbuds: dict) -> None:
    _bootstrap(client, world_earbuds)
    client.post(
        "/v1/ledger/reservations",
        json={
            "merchant_id": "mch_aurum",
            "incident_id": "inc_right_audio",
            "amount_minor": 499900,
            "idempotency_key": "agent_fail_v1",
        },
    )
    failed = client.post(
        "/v1/ledger/reservations/fail",
        json={"merchant_id": "mch_aurum", "idempotency_key": "agent_fail_v1"},
    )
    assert failed.status_code == 200
    assert failed.json()["status"] == RemedyStatus.FAILED.value

    retry = client.post(
        "/v1/ledger/reservations",
        json={
            "merchant_id": "mch_aurum",
            "incident_id": "inc_right_audio",
            "amount_minor": 499900,
            "idempotency_key": "agent_retry_v1",
        },
    )
    assert retry.status_code == 200


def test_idempotent_reserve_replay(client: TestClient, world_earbuds: dict) -> None:
    _bootstrap(client, world_earbuds)
    payload = {
        "merchant_id": "mch_aurum",
        "incident_id": "inc_right_audio",
        "amount_minor": 499900,
        "idempotency_key": "agent_same_key_v1",
    }
    first = client.post("/v1/ledger/reservations", json=payload)
    second = client.post("/v1/ledger/reservations", json=payload)
    assert first.status_code == 200
    assert second.status_code == 200
    assert first.json()["remedy_request_id"] == second.json()["remedy_request_id"]
    position = client.get(
        "/v1/ledger/entitlements/inc_right_audio",
        params={"merchant_id": "mch_aurum"},
    )
    assert position.json()["reserved_entitlement_minor"] == 499900
