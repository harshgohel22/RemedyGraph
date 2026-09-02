from dataclasses import dataclass
from typing import Protocol

from app.core.config import settings
from app.domain.enums import IncidentRelation, MatchReason
from app.schemas.claims import CompiledClaim
from app.schemas.incidents import LinkDraft
from app.schemas.retrieval import RetrievalHit


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


class HeuristicIncidentLinker:
    """Deterministic stand-in until a live LLM is wired. Still must pass grounding."""

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
    return HeuristicIncidentLinker()
