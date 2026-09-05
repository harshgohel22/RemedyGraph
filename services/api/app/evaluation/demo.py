"""Walk the earbud story the way a judge would: prevent the duplicate, then pay a first claim."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from app.evaluation.runner import eval_client

FIXTURES = Path(__file__).resolve().parents[2] / "tests" / "fixtures"


def _compile(client, world: dict, body: str, order_reference: str | None, key: str) -> str:
    assert client.post("/v1/ingest/world", json=world).status_code == 200
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
    return compiled.json()["claim"]["claim_id"]


def _print_audit(client, title: str) -> None:
    print(f"\n{title}")
    audit = client.get("/v1/audit", params={"merchant_id": "mch_aurum"}).json()
    for event in audit["events"]:
        print(f"   {event['event_type']}")


def main() -> None:
    world = json.loads((FIXTURES / "world_earbuds.json").read_text())
    with eval_client() as client:
        print("1. Duplicate path — WhatsApp replacement already settled, email asks for cash")
        prevent_id = _compile(
            client,
            world,
            "The right side produces no audio. Please refund me.",
            None,
            "demo_prevent_v1",
        )
        blocked = client.post(f"/v1/evaluate/claims/{prevent_id}/execute").json()
        decision = blocked["evaluation"]["decision"]
        print(f"   decision={decision['decision']}")
        print(f"   relation={blocked['evaluation']['link']['relation']}")
        print(f"   avoidable=₹{decision['avoidable_overcompensation_minor'] / 100:.2f}")
        print(f"   executed={blocked['executed']}")
        _print_audit(client, "   Audit (prevent path)")

    with eval_client() as client:
        print("\n2. First-claim path — no history, attested order, cash refund is allowed")
        fresh = json.loads((FIXTURES / "world_earbuds.json").read_text())
        fresh["support_messages"] = []
        fresh["historical_remedies"] = []
        allow_id = _compile(
            client,
            fresh,
            "The right earbud has stopped working. Please refund me.",
            "ord_1001",
            "demo_allow_v1",
        )
        paid = client.post(f"/v1/evaluate/claims/{allow_id}/execute").json()
        print(f"   decision={paid['evaluation']['decision']['decision']}")
        print(f"   executed={paid['executed']}")
        print(f"   refund_status={paid['refund']['status'] if paid['refund'] else None}")
        _print_audit(client, "   Audit (allow path)")


if __name__ == "__main__":
    main()
