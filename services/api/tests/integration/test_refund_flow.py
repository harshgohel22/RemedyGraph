import json

from fastapi.testclient import TestClient

from app.core.config import settings
from app.domain.enums import RemedyStatus
from app.services.razorpay_client import FakeRazorpayGateway
from app.services.webhook_signature import sign_webhook_body


def _bootstrap(client: TestClient) -> None:
    world = json.loads(
        __import__("pathlib").Path(__file__).resolve().parents[1].joinpath("fixtures/world_earbuds.json").read_text()
    )
    assert client.post("/v1/ingest/world", json=world).status_code == 200
    opened = client.post(
        "/v1/ledger/entitlements",
        json={
            "merchant_id": "mch_aurum",
            "incident_id": "inc_right_audio",
            "allowed_entitlement_minor": 499900,
        },
    )
    assert opened.status_code == 200


def _refund_payload() -> dict:
    return {
        "merchant_id": "mch_aurum",
        "incident_id": "inc_right_audio",
        "razorpay_payment_id": "pay_test_asha_1001",
        "amount_minor": 499900,
        "idempotency_key": "refund_asha_email_v1",
    }


def test_cash_refund_reserves_then_settles_when_gateway_processed(
    client: TestClient, razorpay: FakeRazorpayGateway
) -> None:
    _bootstrap(client)
    response = client.post("/v1/refunds", json=_refund_payload())
    assert response.status_code == 200
    assert response.json()["status"] == RemedyStatus.SETTLED.value
    assert len([c for c in razorpay.calls if c[0] == "create"]) == 1
    position = client.get(
        "/v1/ledger/entitlements/inc_right_audio",
        params={"merchant_id": "mch_aurum"},
    )
    assert position.json()["settled_entitlement_minor"] == 499900
    assert position.json()["reserved_entitlement_minor"] == 0


def test_same_idempotency_key_does_not_create_two_razorpay_refunds(
    client: TestClient, razorpay: FakeRazorpayGateway
) -> None:
    _bootstrap(client)
    first = client.post("/v1/refunds", json=_refund_payload())
    second = client.post("/v1/refunds", json=_refund_payload())
    assert first.status_code == 200
    assert second.status_code == 200
    assert first.json()["refund_id"] == second.json()["refund_id"]
    assert len([c for c in razorpay.calls if c[0] == "create"]) == 1


def test_timeout_keeps_reservation_and_retry_reuses_key(
    client: TestClient, razorpay: FakeRazorpayGateway
) -> None:
    _bootstrap(client)
    razorpay.timeout_next = True
    first = client.post("/v1/refunds", json=_refund_payload())
    assert first.status_code == 200
    assert first.json()["status"] == RemedyStatus.RECONCILIATION_REQUIRED.value
    held = client.get(
        "/v1/ledger/entitlements/inc_right_audio",
        params={"merchant_id": "mch_aurum"},
    )
    assert held.json()["reserved_entitlement_minor"] == 499900
    second = client.post("/v1/refunds", json=_refund_payload())
    assert second.status_code == 200
    assert second.json()["status"] == RemedyStatus.SETTLED.value
    assert second.json()["refund_id"] == first.json()["refund_id"]


def test_rejected_refund_releases_reservation(
    client: TestClient, razorpay: FakeRazorpayGateway
) -> None:
    _bootstrap(client)
    razorpay.reject_next = True
    response = client.post("/v1/refunds", json=_refund_payload())
    assert response.status_code == 409
    position = client.get(
        "/v1/ledger/entitlements/inc_right_audio",
        params={"merchant_id": "mch_aurum"},
    )
    assert position.json()["reserved_entitlement_minor"] == 0
    assert position.json()["remaining_minor"] == 499900


def test_uncaptured_payment_is_not_refunded(client: TestClient, world_earbuds: dict) -> None:
    world_earbuds["razorpay_payments"][0]["status"] = "authorized"
    client.post("/v1/ingest/world", json=world_earbuds)
    client.post(
        "/v1/ledger/entitlements",
        json={
            "merchant_id": "mch_aurum",
            "incident_id": "inc_right_audio",
            "allowed_entitlement_minor": 499900,
        },
    )
    response = client.post("/v1/refunds", json=_refund_payload())
    assert response.status_code == 409


def _signed_webhook(refund_id: str, event: str, event_id: str) -> tuple[bytes, dict]:
    payload = {
        "event": event,
        "payload": {
            "refund": {
                "entity": {
                    "id": refund_id,
                    "payment_id": "pay_test_asha_1001",
                    "amount": 499900,
                    "status": "processed" if event == "refund.processed" else "failed",
                }
            }
        },
    }
    raw = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    signature = sign_webhook_body(raw, settings.razorpay_webhook_secret)
    headers = {
        "X-Razorpay-Signature": signature,
        "X-Razorpay-Event-Id": event_id,
        "Content-Type": "application/json",
    }
    return raw, headers


def test_webhook_settles_pending_refund(client: TestClient, razorpay: FakeRazorpayGateway) -> None:
    _bootstrap(client)
    razorpay.immediate_status = "created"
    created = client.post("/v1/refunds", json=_refund_payload())
    assert created.json()["status"] == RemedyStatus.PROCESSING.value
    held = client.get(
        "/v1/ledger/entitlements/inc_right_audio",
        params={"merchant_id": "mch_aurum"},
    )
    assert held.json()["reserved_entitlement_minor"] == 499900

    raw, headers = _signed_webhook(created.json()["razorpay_refund_id"], "refund.processed", "evt_1")
    hook = client.post("/v1/webhooks/razorpay", content=raw, headers=headers)
    assert hook.status_code == 200
    assert hook.json()["duplicate"] is False
    settled = client.get(
        "/v1/ledger/entitlements/inc_right_audio",
        params={"merchant_id": "mch_aurum"},
    )
    assert settled.json()["settled_entitlement_minor"] == 499900
    assert settled.json()["reserved_entitlement_minor"] == 0


def test_duplicate_webhook_does_not_double_settle(client: TestClient, razorpay: FakeRazorpayGateway) -> None:
    _bootstrap(client)
    razorpay.immediate_status = "created"
    created = client.post("/v1/refunds", json=_refund_payload())
    raw, headers = _signed_webhook(created.json()["razorpay_refund_id"], "refund.processed", "evt_dup")
    first = client.post("/v1/webhooks/razorpay", content=raw, headers=headers)
    second = client.post("/v1/webhooks/razorpay", content=raw, headers=headers)
    assert first.json()["duplicate"] is False
    assert second.json()["duplicate"] is True
    position = client.get(
        "/v1/ledger/entitlements/inc_right_audio",
        params={"merchant_id": "mch_aurum"},
    )
    assert position.json()["settled_entitlement_minor"] == 499900


def test_failed_webhook_after_settle_does_not_crash_or_unpay(
    client: TestClient, razorpay: FakeRazorpayGateway
) -> None:
    """Out-of-order refund.failed must not raise ReservationNotActive or unwind a settled ledger."""

    _bootstrap(client)
    created = client.post("/v1/refunds", json=_refund_payload())
    assert created.json()["status"] == RemedyStatus.SETTLED.value
    raw, headers = _signed_webhook(created.json()["razorpay_refund_id"], "refund.failed", "evt_late_fail")
    hook = client.post("/v1/webhooks/razorpay", content=raw, headers=headers)
    assert hook.status_code == 200
    position = client.get(
        "/v1/ledger/entitlements/inc_right_audio",
        params={"merchant_id": "mch_aurum"},
    )
    assert position.json()["settled_entitlement_minor"] == 499900
    assert position.json()["reserved_entitlement_minor"] == 0


def test_failed_webhook_releases_active_reservation(
    client: TestClient, razorpay: FakeRazorpayGateway
) -> None:
    _bootstrap(client)
    razorpay.immediate_status = "created"
    created = client.post("/v1/refunds", json=_refund_payload())
    assert created.json()["status"] == RemedyStatus.PROCESSING.value
    raw, headers = _signed_webhook(created.json()["razorpay_refund_id"], "refund.failed", "evt_fail")
    hook = client.post("/v1/webhooks/razorpay", content=raw, headers=headers)
    assert hook.status_code == 200
    position = client.get(
        "/v1/ledger/entitlements/inc_right_audio",
        params={"merchant_id": "mch_aurum"},
    )
    assert position.json()["reserved_entitlement_minor"] == 0
    assert position.json()["settled_entitlement_minor"] == 0
    assert position.json()["remaining_minor"] == 499900


def test_invalid_webhook_signature_is_rejected(client: TestClient, razorpay: FakeRazorpayGateway) -> None:
    _bootstrap(client)
    razorpay.immediate_status = "created"
    created = client.post("/v1/refunds", json=_refund_payload())
    raw, headers = _signed_webhook(created.json()["razorpay_refund_id"], "refund.processed", "evt_bad")
    headers["X-Razorpay-Signature"] = "deadbeef"
    response = client.post("/v1/webhooks/razorpay", content=raw, headers=headers)
    assert response.status_code == 400
    held = client.get(
        "/v1/ledger/entitlements/inc_right_audio",
        params={"merchant_id": "mch_aurum"},
    )
    assert held.json()["reserved_entitlement_minor"] == 499900
