from copy import deepcopy
from datetime import datetime, timezone

from fastapi.testclient import TestClient

from app.domain.enums import Decision, RemedyStatus


def _compile(
    client: TestClient,
    world: dict,
    *,
    body: str,
    order_reference: str | None,
    key: str,
) -> str:
    client.post("/v1/ingest/world", json=world)
    ingested = client.post(
        "/v1/ingest/attempts",
        json={
            "message": {
                "merchant_id": "mch_aurum",
                "customer_id": "cus_asha",
                "channel": "EMAIL",
                "body": body,
                "occurred_at": datetime(2026, 8, 20, 9, 0, tzinfo=timezone.utc).isoformat(),
                "order_reference": order_reference,
                "external_message_id": key,
            },
            "proposal": {
                "remedy_type": "CASH_REFUND",
                "amount_minor": 499900,
                "entitlement_consumption_minor": 499900,
                "currency": "INR",
                "idempotency_key": key,
            },
        },
    )
    compiled = client.post(
        "/v1/claims/compile",
        json={"support_message_id": ingested.json()["support_message_id"]},
    )
    assert compiled.status_code == 200
    return compiled.json()["claim"]["claim_id"]


def test_execute_blocks_duplicate_email_after_whatsapp(
    client: TestClient, world_earbuds: dict
) -> None:
    claim_id = _compile(
        client,
        world_earbuds,
        body="The right side produces no audio. Please refund me.",
        order_reference=None,
        key="remedy_exec_prevent_v1",
    )
    response = client.post(f"/v1/evaluate/claims/{claim_id}/execute")
    assert response.status_code == 200
    body = response.json()
    assert body["executed"] is False
    assert body["blocked_reason"] == Decision.PREVENT_DUPLICATE.value
    assert body["refund"] is None
    assert body["evaluation"]["decision"]["decision"] == Decision.PREVENT_DUPLICATE.value
    ledger = client.get(
        "/v1/ledger/entitlements/inc_msg_wa_001",
        params={"merchant_id": "mch_aurum"},
    )
    assert ledger.json()["reserved_entitlement_minor"] == 0
    assert ledger.json()["settled_entitlement_minor"] == 499900


def test_execute_allows_first_claim_and_settles_refund(
    client: TestClient, world_earbuds: dict
) -> None:
    world = deepcopy(world_earbuds)
    world["support_messages"] = []
    world["historical_remedies"] = []
    claim_id = _compile(
        client,
        world,
        body="The right earbud has stopped working. Please refund me.",
        order_reference="ord_1001",
        key="remedy_exec_allow_v1",
    )
    response = client.post(f"/v1/evaluate/claims/{claim_id}/execute")
    assert response.status_code == 200
    body = response.json()
    assert body["executed"] is True
    assert body["evaluation"]["decision"]["decision"] == Decision.ALLOW.value
    assert body["refund"]["status"] == RemedyStatus.SETTLED.value
    assert body["refund"]["amount_minor"] == 499900
    ledger = client.get(
        f"/v1/ledger/entitlements/{body['evaluation']['incident_id']}",
        params={"merchant_id": "mch_aurum"},
    )
    assert ledger.json()["settled_entitlement_minor"] == 499900
    assert ledger.json()["reserved_entitlement_minor"] == 0
    stored = client.get(f"/v1/ingest/attempts/{body['evaluation']['remedy_request_id']}")
    assert stored.json()["status"] == RemedyStatus.SETTLED.value
