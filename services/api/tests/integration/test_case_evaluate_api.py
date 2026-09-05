from copy import deepcopy
from datetime import datetime, timezone

from fastapi.testclient import TestClient

from app.domain.enums import Decision, IncidentRelation, ReasonCode, RemedyStatus


def _email_attempt(*, order_reference: str | None = None, key: str = "remedy_email_refund_v1") -> dict:
    return {
        "message": {
            "merchant_id": "mch_aurum",
            "customer_id": "cus_asha",
            "channel": "EMAIL",
            "body": "The right side produces no audio. Please refund me.",
            "occurred_at": datetime(2026, 8, 20, 9, 0, tzinfo=timezone.utc).isoformat(),
            "order_reference": order_reference,
            "external_message_id": "email_2001",
        },
        "proposal": {
            "remedy_type": "CASH_REFUND",
            "amount_minor": 499900,
            "entitlement_consumption_minor": 499900,
            "currency": "INR",
            "idempotency_key": key,
        },
    }


def _compile_email(client: TestClient, world: dict, **attempt_kwargs: object) -> str:
    client.post("/v1/ingest/world", json=world)
    ingested = client.post("/v1/ingest/attempts", json=_email_attempt(**attempt_kwargs))
    compiled = client.post(
        "/v1/claims/compile",
        json={"support_message_id": ingested.json()["support_message_id"]},
    )
    assert compiled.status_code == 200
    return compiled.json()["claim"]["claim_id"]


def test_email_refund_is_prevented_after_whatsapp_replacement(
    client: TestClient, world_earbuds: dict
) -> None:
    claim_id = _compile_email(client, world_earbuds)
    response = client.post(f"/v1/evaluate/claims/{claim_id}")
    assert response.status_code == 200
    body = response.json()
    assert body["incident_id"] == "inc_msg_wa_001"
    assert body["remaining_minor"] == 0
    assert body["link"]["relation"] == IncidentRelation.SAME_INCIDENT.value
    decision = body["decision"]
    assert decision["decision"] == Decision.PREVENT_DUPLICATE.value
    assert ReasonCode.ENTITLEMENT_EXHAUSTED.value in decision["reason_codes"]
    assert decision["avoidable_overcompensation_minor"] == 499900
    assert decision["remaining_after_minor"] == 0

    ledger = client.get(
        "/v1/ledger/entitlements/inc_msg_wa_001",
        params={"merchant_id": "mch_aurum"},
    )
    assert ledger.status_code == 200
    assert ledger.json()["settled_entitlement_minor"] == 499900
    assert ledger.json()["reserved_entitlement_minor"] == 0
    assert ledger.json()["remaining_minor"] == 0

    stored = client.get(f"/v1/ingest/attempts/{body['remedy_request_id']}")
    assert stored.json()["incident_id"] == "inc_msg_wa_001"
    assert stored.json()["status"] == RemedyStatus.PROPOSED.value


def test_evaluate_does_not_double_seed_settled(
    client: TestClient, world_earbuds: dict
) -> None:
    claim_id = _compile_email(client, world_earbuds)
    first = client.post(f"/v1/evaluate/claims/{claim_id}")
    second = client.post(f"/v1/evaluate/claims/{claim_id}")
    assert first.status_code == 200
    assert second.status_code == 200
    assert second.json()["decision"]["decision"] == Decision.PREVENT_DUPLICATE.value
    ledger = client.get(
        "/v1/ledger/entitlements/inc_msg_wa_001",
        params={"merchant_id": "mch_aurum"},
    )
    assert ledger.json()["settled_entitlement_minor"] == 499900


def test_new_claim_with_attested_order_is_allowed_without_history(
    client: TestClient, world_earbuds: dict
) -> None:
    world = deepcopy(world_earbuds)
    world["support_messages"] = []
    world["historical_remedies"] = []
    claim_id = _compile_email(client, world, order_reference="ord_1001", key="remedy_first_refund_v1")
    response = client.post(f"/v1/evaluate/claims/{claim_id}")
    assert response.status_code == 200
    body = response.json()
    assert body["link"]["relation"] == IncidentRelation.NEW_INCIDENT.value
    assert body["remaining_minor"] == 499900
    assert body["decision"]["decision"] == Decision.ALLOW.value
    assert body["decision"]["remaining_after_minor"] == 0
    ledger = client.get(
        f"/v1/ledger/entitlements/{body['incident_id']}",
        params={"merchant_id": "mch_aurum"},
    )
    assert ledger.json()["settled_entitlement_minor"] == 0
    assert ledger.json()["reserved_entitlement_minor"] == 0
    assert ledger.json()["remaining_minor"] == 499900
