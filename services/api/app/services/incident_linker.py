from dataclasses import dataclass
from typing import Protocol

from app.core.config import settings
from app.domain.enums import IncidentRelation, MatchReason
from app.schemas.claims import CompiledClaim
from app.schemas.incidents import LinkDraft
from app.schemas.retrieval import RetrievalHit
from app.services.llm_structured import OpenAIStructuredParser, StructuredParser


@dataclass(frozen=True)
class LinkRequest:
    """What the model may see. No catalog. No ledger. No incident id to mint."""

    claim: CompiledClaim
    hit: RetrievalHit | None


class IncidentLinker(Protocol):
    model_version: str

    def assess(self, request: LinkRequest) -> LinkDraft: ...


class FakeIncidentLinker:
    """Test double. Returns a programmed draft so tests can simulate a reckless SAME."""

    model_version = "fake-v1"

    def __init__(self, draft: LinkDraft | None = None) -> None:
        self.draft = draft or LinkDraft(relation=IncidentRelation.UNCERTAIN, confidence=0.0)
        self.calls: list[LinkRequest] = []

    def assess(self, request: LinkRequest) -> LinkDraft:
        self.calls.append(request)
        return self.draft


_LINK_SYSTEM = """You compare one grounded customer claim to one prior support case.

You do not mint incident ids. You do not authorize refunds or write a ledger.
SAME_INCIDENT only when the same physical defect is clearly the same event.
If attested order ids conflict, return NEW_INCIDENT.
If you cannot prove SAME, return UNCERTAIN with requires_review=true.
Prefer UNCERTAIN over a reckless SAME. A false SAME blocks a legitimate new claim.
Do not treat "the customer has only one order" as evidence.
"""


class LLMIncidentLinker:
    """Hosted model relation draft. ground_link still downgrades unsafe SAME after this returns."""

    model_version = "openai-link-v1"

    def __init__(self, parser: StructuredParser | None = None) -> None:
        self.parser = parser or OpenAIStructuredParser()

    def assess(self, request: LinkRequest) -> LinkDraft:
        if request.hit is None:
            return LinkDraft(
                relation=IncidentRelation.NEW_INCIDENT,
                confidence=1.0,
                evidence_for=["no prior cases for this customer"],
            )
        hit = request.hit
        claim = request.claim
        user = (
            "grounded_claim:\n"
            f"  order_reference: {claim.order_reference}\n"
            f"  unit_reference: {claim.unit_reference}\n"
            f"  incident_type: {claim.incident_type}\n"
            f"  incident_description: {claim.incident_description}\n"
            "prior_case:\n"
            f"  channel: {hit.channel.value}\n"
            f"  order_reference: {hit.order_reference}\n"
            f"  overlap_score: {hit.overlap_score}\n"
            f"  shared_tokens: {hit.shared_tokens}\n"
            f"  match_reasons: {[reason.value for reason in hit.match_reasons]}\n"
            f"  body: {hit.body}\n"
            f"  remedies: {[{'type': r.remedy_type.value, 'status': r.status.value, 'unit': r.item_unit_id} for r in hit.remedies]}\n"
        )
        try:
            return self.parser.parse(system=_LINK_SYSTEM, user=user, response_model=LinkDraft)
        except Exception:
            return LinkDraft(
                relation=IncidentRelation.UNCERTAIN,
                confidence=0.0,
                evidence_against=["linker unavailable; fail closed"],
                requires_review=True,
            )


class HeuristicIncidentLinker:
    """Offline stand-in. Still must pass grounding. Used for tests and frozen held-out eval."""

    model_version = "heuristic-v1"

    def assess(self, request: LinkRequest) -> LinkDraft:
        hit = request.hit
        if hit is None:
            return LinkDraft(
                relation=IncidentRelation.NEW_INCIDENT,
                confidence=1.0,
                evidence_for=["no prior cases for this customer"],
            )

        order_match = MatchReason.ORDER_REFERENCE_MATCH in hit.match_reasons or bool(
            request.claim.order_reference
            and hit.order_reference
            and request.claim.order_reference == hit.order_reference
        )
        orders_conflict = bool(
            request.claim.order_reference
            and hit.order_reference
            and request.claim.order_reference != hit.order_reference
        )
        if orders_conflict:
            return LinkDraft(
                relation=IncidentRelation.NEW_INCIDENT,
                confidence=0.85,
                evidence_against=["candidate is a different attested order"],
                contradictory_fields=["order_reference"],
            )

        has_remedy = bool(hit.remedies)
        has_shared = bool(hit.shared_tokens)
        if has_remedy and has_shared:
            return LinkDraft(
                relation=IncidentRelation.SAME_INCIDENT,
                confidence=0.78,
                evidence_for=[
                    "prior remedy on this customer",
                    "shared description tokens",
                ],
            )
        if order_match and (has_shared or has_remedy):
            return LinkDraft(
                relation=IncidentRelation.SAME_INCIDENT,
                confidence=0.8,
                evidence_for=["same attested order", "supporting overlap or prior remedy"],
            )
        if has_shared:
            return LinkDraft(
                relation=IncidentRelation.UNCERTAIN,
                confidence=0.45,
                evidence_for=["some shared tokens"],
                evidence_against=["not enough to prove the same incident"],
                requires_review=True,
            )
        return LinkDraft(
            relation=IncidentRelation.NEW_INCIDENT,
            confidence=0.7,
            evidence_for=["prior case does not overlap this claim"],
            evidence_against=["no shared tokens"],
        )


def build_linker() -> IncidentLinker:
    mode = settings.incident_linker_mode.lower()
    if mode == "fake":
        return FakeIncidentLinker()
    if mode == "llm":
        return LLMIncidentLinker()
    return HeuristicIncidentLinker()
