from app.schemas.ingest import IngestAttemptRequest, IngestAttemptResponse, StoredAttempt
from app.schemas.world import WorldIngestRequest, WorldIngestResponse


class IngestError(Exception):
    def __init__(self, message: str, status_code: int = 400) -> None:
        super().__init__(message)
        self.message = message
        self.status_code = status_code


class MerchantNotFound(IngestError):
    def __init__(self, merchant_id: str) -> None:
        super().__init__(f"merchant not found: {merchant_id}", status_code=404)


class CustomerNotFound(IngestError):
    def __init__(self, customer_id: str) -> None:
        super().__init__(f"customer not found: {customer_id}", status_code=404)


class AttemptNotFound(IngestError):
    def __init__(self, remedy_request_id: str) -> None:
        super().__init__(f"attempt not found: {remedy_request_id}", status_code=404)


class SupportMessageNotFound(IngestError):
    def __init__(self, support_message_id: str) -> None:
        super().__init__(f"support message not found: {support_message_id}", status_code=404)


class ClaimNotFound(IngestError):
    def __init__(self, claim_id: str) -> None:
        super().__init__(f"claim not found: {claim_id}", status_code=404)


class LinkNotFound(IngestError):
    def __init__(self, claim_id: str) -> None:
        super().__init__(f"incident link not found: {claim_id}", status_code=404)


class AttemptAlreadySettled(IngestError):
    def __init__(self, remedy_request_id: str) -> None:
        super().__init__(f"attempt already settled: {remedy_request_id}", status_code=409)


class EntitlementCapUnknown(IngestError):
    def __init__(self) -> None:
        super().__init__(
            "cannot determine allowed entitlement without an attested order",
            status_code=422,
        )


class MerchantExists(IngestError):
    def __init__(self, merchant_id: str) -> None:
        super().__init__(
            f"merchant already exists: {merchant_id}; set replace=true to rebuild the world",
            status_code=409,
        )


class IdempotencyConflict(IngestError):
    def __init__(self, idempotency_key: str) -> None:
        super().__init__(
            f"idempotency key already used with a different payload: {idempotency_key}",
            status_code=409,
        )


class WorldValidationError(IngestError):
    def __init__(self, message: str) -> None:
        super().__init__(message, status_code=422)


class PaymentNotFound(IngestError):
    def __init__(self, payment_id: str) -> None:
        super().__init__(f"payment not found: {payment_id}", status_code=404)


class PaymentNotRefundable(IngestError):
    def __init__(self, reason: str) -> None:
        super().__init__(reason, status_code=409)


class InvalidWebhookSignature(IngestError):
    def __init__(self) -> None:
        super().__init__("invalid webhook signature", status_code=400)


class RefundPending(IngestError):
    def __init__(self, message: str) -> None:
        super().__init__(message, status_code=202)

