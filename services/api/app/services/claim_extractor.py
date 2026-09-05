from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from app.core.config import settings
from app.domain.enums import Channel, IncidentType
from app.schemas.claims import ClaimDraft, ExtractedFact
from app.services.llm_structured import OpenAIStructuredParser, StructuredParser


@dataclass(frozen=True)
class ExtractRequest:
    """What the model may see. No catalog. No ledger. No claim_id."""

    customer_id: str
    channel: Channel
    body: str
    occurred_at: datetime
    ingest_order_reference: str | None


class ClaimExtractor(Protocol):
    def extract(self, request: ExtractRequest) -> ClaimDraft: ...


class FakeClaimExtractor:
    """Test double. Returns a programmed draft so tests can simulate hallucination."""

    def __init__(self, draft: ClaimDraft | None = None) -> None:
        self.draft = draft or ClaimDraft(incident_description="stub")
        self.calls: list[ExtractRequest] = []

    def extract(self, request: ExtractRequest) -> ClaimDraft:
        self.calls.append(request)
        return self.draft


_CLAIM_SYSTEM = """You extract a customer-support incident claim as structured data.

You do not authorize money, refunds, replacements, or ledger writes.
You do not invent order, unit, product, payment, or claim identifiers.
If an identifier is not written in the customer message (or the ingest order reference), leave it null.
requested_amount_minor is integer paise. Set it only if that exact integer appears in the message. Do not convert rupees to paise.
unknown_fields must list every identifier or amount you left null.
incident_description restates the defect in one or two sentences. It is not a policy decision.
"""


class LLMClaimExtractor:
    """Hosted model draft generator. Grounding still drops unattested IDs after this returns."""

    def __init__(self, parser: StructuredParser | None = None) -> None:
        self.parser = parser or OpenAIStructuredParser()

    def extract(self, request: ExtractRequest) -> ClaimDraft:
        user = (
            f"channel: {request.channel.value}\n"
            f"occurred_at: {request.occurred_at.isoformat()}\n"
            f"ingest_order_reference: {request.ingest_order_reference or 'null'}\n"
            f"message:\n{request.body}"
        )
        try:
            return self.parser.parse(system=_CLAIM_SYSTEM, user=user, response_model=ClaimDraft)
        except Exception:
            return ClaimDraft(
                incident_description=request.body,
                incident_time=request.occurred_at.isoformat(),
                order_reference=None,
                product_reference=None,
                unit_reference=None,
                requested_amount_minor=None,
                unknown_fields=[
                    "order_reference",
                    "product_reference",
                    "unit_reference",
                    "requested_amount_minor",
                ],
            )


class HeuristicClaimExtractor:
    """Offline stand-in. Still must pass grounding. Used for tests and frozen held-out eval."""

    def extract(self, request: ExtractRequest) -> ClaimDraft:
        body = request.body
        lowered = body.lower()
        facts: list[ExtractedFact] = []

        incident_type = _guess_incident_type(lowered)
        if incident_type is not None:
            facts.append(
                ExtractedFact(
                    field="incident_type",
                    value=incident_type.value,
                    source_text=body[:160],
                )
            )

        requested_remedy = _guess_remedy(lowered)
        order_reference = request.ingest_order_reference
        unknown: list[str] = []
        if order_reference is None:
            unknown.append("order_reference")
        unknown.extend(["product_reference", "unit_reference", "requested_amount_minor"])
        if incident_type is None:
            unknown.append("incident_type")

        return ClaimDraft(
            order_reference=order_reference,
            product_reference=None,
            unit_reference=None,
            incident_type=incident_type,
            incident_description=body,
            incident_time=request.occurred_at.isoformat(),
            requested_remedy=requested_remedy,
            requested_amount_minor=None,
            extracted_facts=facts,
            unknown_fields=unknown,
            model_confidence=None,
        )


def build_extractor() -> ClaimExtractor:
    mode = settings.claim_compiler_mode.lower()
    if mode == "fake":
        return FakeClaimExtractor()
    if mode == "llm":
        return LLMClaimExtractor()
    return HeuristicClaimExtractor()


def _guess_incident_type(lowered: str) -> IncidentType | None:
    if any(token in lowered for token in ("wrong item", "not what i ordered", "different product")):
        return IncidentType.WRONG_ITEM
    if any(token in lowered for token in ("missing", "didn't receive", "did not receive", "incomplete")):
        return IncidentType.MISSING_ITEM
    if any(token in lowered for token in ("damaged", "cracked", "smashed", "broken on arrival")):
        return IncidentType.DAMAGED_ON_ARRIVAL
    if any(
        token in lowered
        for token in ("no audio", "stopped working", "not working", "dead", "no sound")
    ):
        return IncidentType.FUNCTIONAL_FAILURE
    return None


def _guess_remedy(lowered: str) -> str | None:
    if "refund" in lowered or "money back" in lowered:
        return "CASH_REFUND"
    if "replacement" in lowered or "send another" in lowered:
        return "REPLACEMENT"
    if "store credit" in lowered or "voucher" in lowered:
        return "STORE_CREDIT"
    return None
