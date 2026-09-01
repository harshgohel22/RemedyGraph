from datetime import datetime, timezone

from fastapi.testclient import TestClient

from app.api.deps import get_claim_extractor
from app.domain.enums import IncidentType
from app.schemas.claims import ClaimDraft
from app.services.claim_extractor import FakeClaimExtractor


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


def test_compile_keeps_ingested_whatsapp_order_reference(
    client: TestClient, world_earbuds: dict
) -> None:
    client.post("/v1/ingest/world", json=world_earbuds)
    response = client.post("/v1/claims/compile", json={"support_message_id": "msg_wa_001"})
    assert response.status_code == 200
    body = response.json()
    assert body["replayed"] is False
    claim = body["claim"]
    assert claim["claim_id"].startswith("clm_")
    assert claim["customer_id"] == "cus_asha"
    assert claim["channel"] == "WHATSAPP"
    assert claim["order_reference"] == "ord_1001"
    assert claim["unit_reference"] is None
    assert claim["incident_type"] == IncidentType.FUNCTIONAL_FAILURE.value
    assert claim["requested_remedy"] == "REPLACEMENT"

    stored = client.get(f"/v1/claims/{claim['claim_id']}")
    assert stored.status_code == 200
    assert stored.json()["claim_id"] == claim["claim_id"]


def test_compile_is_idempotent_per_message(client: TestClient, world_earbuds: dict) -> None:
    client.post("/v1/ingest/world", json=world_earbuds)
    first = client.post("/v1/claims/compile", json={"support_message_id": "msg_wa_001"})
    second = client.post("/v1/claims/compile", json={"support_message_id": "msg_wa_001"})
    assert first.status_code == 200
    assert second.status_code == 200
    assert second.json()["replayed"] is True
    assert second.json()["claim"]["claim_id"] == first.json()["claim"]["claim_id"]


def test_email_without_order_id_stays_unknown(client: TestClient, world_earbuds: dict) -> None:
    client.post("/v1/ingest/world", json=world_earbuds)
    ingested = client.post("/v1/ingest/attempts", json=_email_attempt())
    message_id = ingested.json()["support_message_id"]
    response = client.post("/v1/claims/compile", json={"support_message_id": message_id})
    assert response.status_code == 200
    claim = response.json()["claim"]
    assert claim["order_reference"] is None
    assert "order_reference" in claim["unknown_fields"]
    assert claim["incident_type"] == IncidentType.FUNCTIONAL_FAILURE.value
    assert claim["requested_remedy"] == "CASH_REFUND"


def test_hallucinated_real_order_id_is_stripped(
    client: TestClient, world_earbuds: dict
) -> None:
    client.post("/v1/ingest/world", json=world_earbuds)
    ingested = client.post("/v1/ingest/attempts", json=_email_attempt())
    message_id = ingested.json()["support_message_id"]
    fake = FakeClaimExtractor(
        ClaimDraft(
            order_reference="ord_1001",
            unit_reference="unit_right",
            incident_type=IncidentType.FUNCTIONAL_FAILURE,
            incident_description="right earbud has no audio",
            requested_remedy="CASH_REFUND",
            requested_amount_minor=499900,
        )
    )
    client.app.dependency_overrides[get_claim_extractor] = lambda: fake
    try:
        response = client.post("/v1/claims/compile", json={"support_message_id": message_id})
    finally:
        client.app.dependency_overrides.pop(get_claim_extractor, None)

    assert response.status_code == 200
    claim = response.json()["claim"]
    assert claim["order_reference"] is None
    assert claim["unit_reference"] is None
    assert claim["requested_amount_minor"] is None
    assert "order_reference" in claim["unknown_fields"]
    assert "unit_reference" in claim["unknown_fields"]
    assert len(fake.calls) == 1
    assert not hasattr(fake.calls[0], "catalog")


def test_unknown_message_is_not_found(client: TestClient) -> None:
    response = client.post("/v1/claims/compile", json={"support_message_id": "msg_missing"})
    assert response.status_code == 404
