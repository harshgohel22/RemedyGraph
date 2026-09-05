from datetime import datetime, timezone

import pytest

from app.core.config import settings
from app.domain.enums import Channel, IncidentRelation, IncidentType
from app.schemas.claims import ClaimDraft
from app.schemas.incidents import LinkDraft
from app.services.claim_extractor import ExtractRequest, LLMClaimExtractor, build_extractor
from app.services.claim_grounding import IdCatalog, ground_draft
from app.services.incident_link_grounding import ground_link
from app.services.incident_linker import LLMIncidentLinker, LinkRequest, build_linker
from app.services.llm_structured import LlmNotConfigured
from tests.unit.test_incident_link import _claim, _hit


class _StubParser:
    def __init__(self, payload: object) -> None:
        self.payload = payload
        self.calls = 0

    def parse(self, *, system: str, user: str, response_model: type) -> object:
        self.calls += 1
        if isinstance(self.payload, Exception):
            raise self.payload
        return self.payload


def _request() -> ExtractRequest:
    return ExtractRequest(
        customer_id="cus_asha",
        channel=Channel.EMAIL,
        body="The right side produces no audio. Please refund me.",
        occurred_at=datetime(2026, 8, 20, 9, 0, tzinfo=timezone.utc),
        ingest_order_reference=None,
    )


def test_llm_extractor_returns_claim_draft_only() -> None:
    draft = ClaimDraft(
        incident_description="Right bud has no audio.",
        incident_type=IncidentType.FUNCTIONAL_FAILURE,
        requested_remedy="CASH_REFUND",
        order_reference="ord_1001",
        unknown_fields=[],
    )
    extractor = LLMClaimExtractor(parser=_StubParser(draft))
    result = extractor.extract(_request())
    assert result is draft
    assert not hasattr(result, "claim_id") or "claim_id" not in result.model_dump()


def test_llm_hallucinated_order_is_dropped_by_grounding() -> None:
    """The model may guess ord_1001. Grounding must still refuse it."""

    draft = ClaimDraft(
        incident_description="Right bud has no audio.",
        order_reference="ord_1001",
        incident_type=IncidentType.FUNCTIONAL_FAILURE,
    )
    extractor = LLMClaimExtractor(parser=_StubParser(draft))
    extracted = extractor.extract(_request())
    grounded = ground_draft(
        claim_id="clm_test",
        customer_id="cus_asha",
        channel=Channel.EMAIL,
        body=_request().body,
        ingest_order_reference=None,
        draft=extracted,
        catalog=IdCatalog(
            order_ids=frozenset({"ord_1001"}),
            product_ids=frozenset({"wireless_earbuds"}),
            unit_ids=frozenset({"unit_right"}),
        ),
    )
    assert grounded.order_reference is None
    assert "order_reference" in grounded.unknown_fields


def test_llm_extractor_fails_closed_when_the_model_errors() -> None:
    extractor = LLMClaimExtractor(parser=_StubParser(RuntimeError("timeout")))
    draft = extractor.extract(_request())
    assert draft.order_reference is None
    assert draft.requested_amount_minor is None
    assert "order_reference" in draft.unknown_fields


def test_llm_linker_reckless_same_is_downgraded() -> None:
    linker = LLMIncidentLinker(
        parser=_StubParser(LinkDraft(relation=IncidentRelation.SAME_INCIDENT, confidence=0.99))
    )
    hit = _hit(shared_tokens=[], order_reference=None, match_reasons=[], remedies=[])
    draft = linker.assess(LinkRequest(claim=_claim(), hit=hit))
    grounded = ground_link(claim=_claim(), hit=hit, draft=draft, model_version=linker.model_version)
    assert grounded.relation is IncidentRelation.UNCERTAIN
    assert grounded.requires_review is True


def test_llm_linker_fails_closed_on_error() -> None:
    linker = LLMIncidentLinker(parser=_StubParser(RuntimeError("timeout")))
    draft = linker.assess(LinkRequest(claim=_claim(), hit=_hit()))
    assert draft.relation is IncidentRelation.UNCERTAIN
    assert draft.requires_review is True


def test_llm_linker_does_not_assess_when_there_is_no_candidate() -> None:
    parser = _StubParser(LinkDraft(relation=IncidentRelation.SAME_INCIDENT, confidence=0.9))
    linker = LLMIncidentLinker(parser=parser)
    draft = linker.assess(LinkRequest(claim=_claim(), hit=None))
    assert draft.relation is IncidentRelation.NEW_INCIDENT
    assert parser.calls == 0


def test_build_extractor_llm_without_key_fails_closed_to_config_error(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "claim_compiler_mode", "llm")
    monkeypatch.setattr(settings, "openai_api_key", "")
    with pytest.raises(LlmNotConfigured):
        build_extractor()


def test_build_linker_llm_without_key_fails_closed_to_config_error(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "incident_linker_mode", "llm")
    monkeypatch.setattr(settings, "openai_api_key", "")
    with pytest.raises(LlmNotConfigured):
        build_linker()
