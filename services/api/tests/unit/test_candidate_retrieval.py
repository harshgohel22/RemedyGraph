from datetime import datetime, timezone

from app.domain.enums import Channel, IncidentType, MatchReason, RemedyStatus, RemedyType
from app.schemas.claims import CompiledClaim
from app.schemas.retrieval import ObservedRemedy
from app.services.candidate_retrieval import RetrievalCase, rank_cases, score_case, tokenize


def _claim(*, order_reference: str | None = None) -> CompiledClaim:
    return CompiledClaim(
        claim_id="clm_email",
        customer_id="cus_asha",
        channel=Channel.EMAIL,
        order_reference=order_reference,
        incident_type=IncidentType.FUNCTIONAL_FAILURE,
        incident_description="The right side produces no audio. Please refund me.",
    )


def _whatsapp_case() -> RetrievalCase:
    return RetrievalCase(
        support_message_id="msg_wa_001",
        channel=Channel.WHATSAPP,
        body="The right earbud has stopped working. Please send a replacement.",
        occurred_at=datetime(2026, 8, 10, 11, 15, tzinfo=timezone.utc),
        order_reference="ord_1001",
        incident_type=IncidentType.FUNCTIONAL_FAILURE,
        remedies=(
            ObservedRemedy(
                remedy_request_id="rrq_repl_001",
                remedy_type=RemedyType.REPLACEMENT,
                status=RemedyStatus.SETTLED,
                amount_minor=499900,
                entitlement_consumption_minor=499900,
                item_unit_id="unit_right",
            ),
        ),
    )


def _invoice_case() -> RetrievalCase:
    return RetrievalCase(
        support_message_id="msg_invoice",
        channel=Channel.EMAIL,
        body="Where is the GST invoice for last month?",
        occurred_at=datetime(2026, 7, 2, 8, 0, tzinfo=timezone.utc),
        order_reference=None,
        incident_type=None,
        remedies=(),
    )


def naive_retrieve_by_order(claim: CompiledClaim, cases: list[RetrievalCase]) -> list[RetrievalCase]:
    """Broken: if the new email has no order id, the WhatsApp replacement disappears."""

    if claim.order_reference is None:
        return []
    return [case for case in cases if case.order_reference == claim.order_reference]


def test_naive_order_filter_misses_the_whatsapp_when_email_has_no_order() -> None:
    claim = _claim(order_reference=None)
    cases = [_whatsapp_case(), _invoice_case()]
    assert naive_retrieve_by_order(claim, cases) == []

    hits = rank_cases(claim, cases, limit=20)
    assert [hit.candidate_id for hit in hits] == ["msg_wa_001", "msg_invoice"]


def test_whatsapp_outscores_unrelated_invoice() -> None:
    hit = score_case(_claim(), _whatsapp_case())
    invoice = score_case(_claim(), _invoice_case())
    assert hit.overlap_score > invoice.overlap_score
    assert MatchReason.SAME_CUSTOMER in hit.match_reasons
    assert MatchReason.SHARED_DESCRIPTION_TOKENS in hit.match_reasons
    assert MatchReason.PRIOR_REMEDY_EXISTS in hit.match_reasons
    assert "right" in hit.shared_tokens
    assert hit.remedies[0].remedy_type is RemedyType.REPLACEMENT


def test_order_match_is_a_bonus_not_a_hard_filter() -> None:
    with_order = score_case(_claim(order_reference="ord_1001"), _whatsapp_case())
    without_order = score_case(_claim(order_reference=None), _whatsapp_case())
    assert MatchReason.ORDER_REFERENCE_MATCH in with_order.match_reasons
    assert MatchReason.ORDER_REFERENCE_MATCH not in without_order.match_reasons
    assert without_order.overlap_score > 0


def test_tokenize_drops_stopwords() -> None:
    tokens = tokenize("Please send me the right earbud")
    assert "please" not in tokens
    assert "right" in tokens
    assert "earbud" in tokens
