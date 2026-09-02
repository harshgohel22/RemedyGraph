from copy import deepcopy
from datetime import datetime, timezone

from fastapi.testclient import TestClient

from app.domain.enums import MatchReason, RemedyType


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


def test_email_claim_retrieves_asha_whatsapp_replacement(
    client: TestClient, world_earbuds: dict
) -> None:
    claim_id = _compile_email(client, world_earbuds)
    response = client.get(f"/v1/claims/{claim_id}/candidates")
    assert response.status_code == 200
    body = response.json()
    assert body["customer_id"] == "cus_asha"
    assert len(body["hits"]) == 1
    hit = body["hits"][0]
    assert hit["candidate_id"] == "msg_wa_001"
    assert hit["channel"] == "WHATSAPP"
    assert hit["order_reference"] == "ord_1001"
    assert MatchReason.SAME_CUSTOMER.value in hit["match_reasons"]
    assert MatchReason.SHARED_DESCRIPTION_TOKENS.value in hit["match_reasons"]
    assert MatchReason.PRIOR_REMEDY_EXISTS.value in hit["match_reasons"]
    assert MatchReason.ORDER_REFERENCE_MATCH.value not in hit["match_reasons"]
    assert hit["remedies"][0]["remedy_type"] == RemedyType.REPLACEMENT.value
    assert hit["remedies"][0]["status"] == "SETTLED"
    assert "right" in hit["shared_tokens"]


def test_other_customer_similar_message_is_not_a_candidate(
    client: TestClient, world_earbuds: dict
) -> None:
    world = deepcopy(world_earbuds)
    world["customers"].append({"customer_id": "cus_ravi", "display_name": "Ravi"})
    world["support_messages"].append(
        {
            "support_message_id": "msg_ravi_wa",
            "customer_id": "cus_ravi",
            "channel": "WHATSAPP",
            "body": "The right earbud has stopped working. Please send a replacement.",
            "occurred_at": "2026-08-11T11:15:00+05:30",
            "order_reference": "ord_1001",
            "external_message_id": "wa_ravi",
        }
    )
    claim_id = _compile_email(client, world)
    hits = client.get(f"/v1/claims/{claim_id}/candidates").json()["hits"]
    ids = {hit["candidate_id"] for hit in hits}
    assert "msg_wa_001" in ids
    assert "msg_ravi_wa" not in ids


def test_compiling_whatsapp_has_no_prior_cases(
    client: TestClient, world_earbuds: dict
) -> None:
    client.post("/v1/ingest/world", json=world_earbuds)
    compiled = client.post("/v1/claims/compile", json={"support_message_id": "msg_wa_001"})
    claim_id = compiled.json()["claim"]["claim_id"]
    response = client.get(f"/v1/claims/{claim_id}/candidates")
    assert response.status_code == 200
    assert response.json()["hits"] == []


def test_unknown_claim_is_not_found(client: TestClient) -> None:
    response = client.get("/v1/claims/clm_missing/candidates")
    assert response.status_code == 404
