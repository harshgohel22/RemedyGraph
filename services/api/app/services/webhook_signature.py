import hashlib
import hmac
import json


def verify_webhook_signature(raw_body: bytes, signature: str, secret: str) -> bool:
    """HMAC-SHA256 over the exact raw body. Never hash re-serialized JSON."""
    if not signature or not secret:
        return False
    expected = hmac.new(secret.encode("utf-8"), raw_body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature)


def sign_webhook_body(raw_body: bytes, secret: str) -> str:
    return hmac.new(secret.encode("utf-8"), raw_body, hashlib.sha256).hexdigest()


def dumps_canonical(payload: dict) -> bytes:
    """Stable bytes for tests. Production verifies whatever Razorpay actually sent."""
    return json.dumps(payload, separators=(",", ":"), ensure_ascii=True).encode("utf-8")
