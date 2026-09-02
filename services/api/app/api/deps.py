from fastapi import Depends
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.services.claim_compiler import ClaimCompiler
from app.services.candidate_retrieval import CandidateRetrieval
from app.services.claim_extractor import ClaimExtractor, build_extractor
from app.services.razorpay_client import FakeRazorpayGateway, RazorpayGateway, build_gateway
from app.services.refund_executor import RefundExecutor
from app.services.webhook_processor import WebhookProcessor

_gateway: RazorpayGateway | None = None
_extractor: ClaimExtractor | None = None


def get_razorpay_gateway() -> RazorpayGateway:
    global _gateway
    if _gateway is None:
        _gateway = build_gateway()
    return _gateway


def override_razorpay_gateway(gateway: RazorpayGateway) -> None:
    global _gateway
    _gateway = gateway


def reset_razorpay_gateway() -> None:
    global _gateway
    _gateway = FakeRazorpayGateway()


def get_refund_executor(
    session: Session = Depends(get_db),
    gateway: RazorpayGateway = Depends(get_razorpay_gateway),
) -> RefundExecutor:
    return RefundExecutor(session, gateway)


def get_webhook_processor(
    session: Session = Depends(get_db),
    executor: RefundExecutor = Depends(get_refund_executor),
) -> WebhookProcessor:
    return WebhookProcessor(session, executor)


def get_claim_extractor() -> ClaimExtractor:
    global _extractor
    if _extractor is None:
        _extractor = build_extractor()
    return _extractor


def reset_claim_extractor() -> None:
    global _extractor
    _extractor = None


def get_claim_compiler(
    session: Session = Depends(get_db),
    extractor: ClaimExtractor = Depends(get_claim_extractor),
) -> ClaimCompiler:
    return ClaimCompiler(session, extractor)


def get_candidate_retrieval(session: Session = Depends(get_db)) -> CandidateRetrieval:
    return CandidateRetrieval(session)
