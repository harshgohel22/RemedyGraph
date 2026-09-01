from dataclasses import dataclass
from typing import Protocol

import httpx

from app.core.config import settings


class RazorpayError(Exception):
    pass


class RazorpayTimeout(RazorpayError):
    pass


class RazorpayRejected(RazorpayError):
    pass


@dataclass(frozen=True)
class RefundResult:
    razorpay_refund_id: str
    payment_id: str
    amount_minor: int
    status: str
    idempotency_key: str


class RazorpayGateway(Protocol):
    def create_refund(
        self,
        payment_id: str,
        amount_minor: int,
        idempotency_key: str,
    ) -> RefundResult: ...

    def fetch_refund(self, razorpay_refund_id: str) -> RefundResult: ...


class FakeRazorpayGateway:
    """In-process Test Mode stand-in. No network. Idempotent on the same key."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, str, int]] = []
        self._by_key: dict[str, RefundResult] = {}
        self._by_id: dict[str, RefundResult] = {}
        self.timeout_next = False
        self.reject_next = False
        self.immediate_status = "processed"

    def create_refund(self, payment_id: str, amount_minor: int, idempotency_key: str) -> RefundResult:
        self.calls.append(("create", payment_id, amount_minor))
        if self.timeout_next:
            self.timeout_next = False
            raise RazorpayTimeout("simulated timeout")
        if self.reject_next:
            self.reject_next = False
            raise RazorpayRejected("simulated rejection")
        existing = self._by_key.get(idempotency_key)
        if existing is not None:
            return existing
        result = RefundResult(
            razorpay_refund_id=f"rfnd_fake_{len(self._by_key) + 1}",
            payment_id=payment_id,
            amount_minor=amount_minor,
            status=self.immediate_status,
            idempotency_key=idempotency_key,
        )
        self._by_key[idempotency_key] = result
        self._by_id[result.razorpay_refund_id] = result
        return result

    def fetch_refund(self, razorpay_refund_id: str) -> RefundResult:
        self.calls.append(("fetch", razorpay_refund_id, 0))
        found = self._by_id.get(razorpay_refund_id)
        if found is None:
            raise RazorpayRejected(f"unknown refund {razorpay_refund_id}")
        return found

    def mark_processed(self, idempotency_key: str) -> RefundResult:
        current = self._by_key[idempotency_key]
        updated = RefundResult(
            razorpay_refund_id=current.razorpay_refund_id,
            payment_id=current.payment_id,
            amount_minor=current.amount_minor,
            status="processed",
            idempotency_key=current.idempotency_key,
        )
        self._by_key[idempotency_key] = updated
        self._by_id[updated.razorpay_refund_id] = updated
        return updated


class LiveRazorpayGateway:
    """Razorpay Test/Live REST. Keys stay on the server. Never called from unit tests."""

    def __init__(self, key_id: str, key_secret: str) -> None:
        self._auth = (key_id, key_secret)

    def create_refund(self, payment_id: str, amount_minor: int, idempotency_key: str) -> RefundResult:
        try:
            response = httpx.post(
                f"https://api.razorpay.com/v1/payments/{payment_id}/refund",
                auth=self._auth,
                headers={
                    "Content-Type": "application/json",
                    "X-Refund-Idempotency": idempotency_key,
                },
                json={"amount": amount_minor},
                timeout=15.0,
            )
        except httpx.TimeoutException as exc:
            raise RazorpayTimeout("razorpay refund timed out") from exc
        if response.status_code >= 400:
            raise RazorpayRejected(response.text)
        body = response.json()
        return RefundResult(
            razorpay_refund_id=body["id"],
            payment_id=body.get("payment_id", payment_id),
            amount_minor=int(body["amount"]),
            status=str(body.get("status", "created")),
            idempotency_key=idempotency_key,
        )

    def fetch_refund(self, razorpay_refund_id: str) -> RefundResult:
        try:
            response = httpx.get(
                f"https://api.razorpay.com/v1/refunds/{razorpay_refund_id}",
                auth=self._auth,
                timeout=15.0,
            )
        except httpx.TimeoutException as exc:
            raise RazorpayTimeout("razorpay fetch timed out") from exc
        if response.status_code >= 400:
            raise RazorpayRejected(response.text)
        body = response.json()
        return RefundResult(
            razorpay_refund_id=body["id"],
            payment_id=body.get("payment_id", ""),
            amount_minor=int(body["amount"]),
            status=str(body.get("status", "created")),
            idempotency_key="",
        )


def build_gateway() -> RazorpayGateway:
    if settings.razorpay_mode == "live" and settings.razorpay_key_id and settings.razorpay_key_secret:
        return LiveRazorpayGateway(settings.razorpay_key_id, settings.razorpay_key_secret)
    return FakeRazorpayGateway()
