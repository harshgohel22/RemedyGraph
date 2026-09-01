from app.services.webhook_signature import sign_webhook_body, verify_webhook_signature


def test_signature_matches_raw_bytes() -> None:
    body = b'{"event":"refund.processed"}'
    secret = "whsec_test"
    signature = sign_webhook_body(body, secret)
    assert verify_webhook_signature(body, signature, secret) is True


def test_signature_fails_if_json_is_reserialized() -> None:
    raw = b'{"event":"refund.processed","payload":{}}'
    secret = "whsec_test"
    signature = sign_webhook_body(raw, secret)
    tampered = b'{"payload":{},"event":"refund.processed"}'
    assert verify_webhook_signature(tampered, signature, secret) is False
