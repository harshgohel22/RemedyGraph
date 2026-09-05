from app.evaluation.schema import HeldOutCase


def expand_world(case: HeldOutCase) -> dict:
    """Build a synthetic merchant world from a compact held-out case. Deterministic."""

    merchant_id = f"mch_{case.case_id}"
    orders = [_order("ord_1001", case.price_minor), *[_order(extra.order_id, extra.unit_price_minor) for extra in case.extra_orders]]
    messages = []
    remedies = []
    for index, prior in enumerate(case.priors, start=1):
        message_id = f"msg_{case.case_id}_p{index}"
        messages.append(
            {
                "support_message_id": message_id,
                "customer_id": "cus_eval",
                "channel": prior.channel.value,
                "body": prior.body,
                "occurred_at": f"2026-08-{index:02d}T11:00:00+05:30",
                "order_reference": prior.order_reference,
                "external_message_id": f"ext_{case.case_id}_p{index}",
            }
        )
        if prior.remedy_type is None or prior.status is None or prior.amount_minor is None:
            continue
        consumption = prior.consumption_minor if prior.consumption_minor is not None else prior.amount_minor
        remedies.append(
            {
                "remedy_request_id": f"rrq_{case.case_id}_p{index}",
                "support_message_id": message_id,
                "customer_id": "cus_eval",
                "remedy_type": prior.remedy_type.value,
                "amount_minor": prior.amount_minor,
                "entitlement_consumption_minor": consumption,
                "currency": "INR",
                "idempotency_key": f"remedy_{case.case_id}_p{index}_v1",
                "status": prior.status.value,
            }
        )
    return {
        "merchant_id": merchant_id,
        "merchant_name": "Held-out Audio",
        "replace": True,
        "customers": [{"customer_id": "cus_eval", "display_name": "Eval Customer"}],
        "orders": orders,
        "support_messages": messages,
        "historical_remedies": remedies,
        "razorpay_payments": [
            {
                "razorpay_payment_id": f"pay_{case.case_id}",
                "razorpay_order_id": "order_eval_1001",
                "internal_order_id": "ord_1001",
                "amount_minor": case.price_minor,
                "status": "captured",
            },
            *[
                {
                    "razorpay_payment_id": f"pay_{case.case_id}_{extra.order_id}",
                    "razorpay_order_id": f"order_eval_{extra.order_id}",
                    "internal_order_id": extra.order_id,
                    "amount_minor": extra.unit_price_minor,
                    "status": "captured",
                }
                for extra in case.extra_orders
            ],
        ],
    }


def expand_attempt(case: HeldOutCase) -> dict:
    incoming = case.incoming
    consumption = incoming.consumption_minor if incoming.consumption_minor is not None else incoming.amount_minor
    return {
        "message": {
            "merchant_id": f"mch_{case.case_id}",
            "customer_id": "cus_eval",
            "channel": incoming.channel.value,
            "body": incoming.body,
            "occurred_at": "2026-08-20T09:00:00+05:30",
            "order_reference": incoming.order_reference,
            "external_message_id": f"ext_{case.case_id}_in",
        },
        "proposal": {
            "remedy_type": incoming.remedy_type.value,
            "amount_minor": incoming.amount_minor,
            "entitlement_consumption_minor": consumption,
            "currency": "INR",
            "idempotency_key": f"remedy_{case.case_id}_in_v1",
        },
    }


def _order(order_id: str, unit_price_minor: int) -> dict:
    return {
        "order_id": order_id,
        "customer_id": "cus_eval",
        "created_at": "2026-07-01T10:00:00+05:30",
        "lines": [
            {
                "order_line_id": f"ol_{order_id}",
                "product_id": "wireless_earbuds",
                "product_name": "Wireless Earbuds",
                "quantity": 1,
                "unit_price_minor": unit_price_minor,
                "units": [{"unit_id": f"unit_{order_id}_right", "parent_unit_id": None}],
            }
        ],
    }
