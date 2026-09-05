from datetime import datetime, timezone

from app.domain.enums import Channel, IncidentRelation, IncidentType, MatchReason, RemedyStatus, RemedyType
from app.schemas.claims import CompiledClaim
from app.schemas.incidents import LinkDraft
from app.schemas.retrieval import ObservedRemedy, RetrievalHit
from app.services.incident_link_grounding import ground_link, incident_id_for_candidate
from app.services.incident_linker import HeuristicIncidentLinker, LinkRequest


def _claim(**overrides: object) -> CompiledClaim:
    payload: dict = {
        "claim_id": "clm_email",
        "customer_id": "cus_asha",
        "channel": Channel.EMAIL,
        "incident_type": IncidentType.FUNCTIONAL_FAILURE,
        "incident_description": "The right side produces no audio. Please refund me.",
    }
    payload.update(overrides)
    return CompiledClaim.model_validate(payload)


def _hit(**overrides: object) -> RetrievalHit:
    payload: dict = {
        "candidate_id": "msg_wa_001",
        "support_message_id": "msg_wa_001",
        "channel": Channel.WHATSAPP,
        "body": "The right earbud has stopped working. Please send a replacement.",
        "occurred_at": datetime(2026, 8, 10, 11, 15, tzinfo=timezone.utc),
        "order_reference": "ord_1001",
        "overlap_score": 4,
        "match_reasons": [MatchReason.SAME_CUSTOMER, MatchReason.SHARED_DESCRIPTION_TOKENS, MatchReason.PRIOR_REMEDY_EXISTS],
        "shared_tokens": ["right"],
        "remedies": [
            ObservedRemedy(
                remedy_request_id="rrq_repl_001",
                remedy_type=RemedyType.REPLACEMENT,
                status=RemedyStatus.SETTLED,
                amount_minor=499900,
                entitlement_consumption_minor=499900,
                item_unit_id="unit_right",
            )
        ],
    }
    payload.update(overrides)
    return RetrievalHit.model_validate(payload)


def _invoice() -> RetrievalHit:
    return _hit(
        candidate_id="msg_invoice",
        support_message_id="msg_invoice",
        channel=Channel.EMAIL,
        body="Where is the GST invoice for last month?",
        order_reference=None,
        overlap_score=0,
        match_reasons=[MatchReason.SAME_CUSTOMER],
        shared_tokens=[],
        remedies=[],
    )


def _same_draft() -> LinkDraft:
    return LinkDraft(relation=IncidentRelation.SAME_INCIDENT, confidence=0.99, evidence_for=["model guessed"])


def naive_same_if_any_candidate(hit: RetrievalHit | None) -> IncidentRelation:
    """Broken: every retrieved prior case becomes SAME_INCIDENT."""

    if hit is None:
        return IncidentRelation.NEW_INCIDENT
    return IncidentRelation.SAME_INCIDENT


def test_naive_marks_unrelated_invoice_as_same() -> None:
    assert naive_same_if_any_candidate(_invoice()) is IncidentRelation.SAME_INCIDENT
    grounded = ground_link(
        claim=_claim(),
        hit=_invoice(),
        draft=_same_draft(),
        model_version="fake",
    )
    assert grounded.relation is IncidentRelation.UNCERTAIN
    assert grounded.requires_review is True
    assert grounded.candidate_incident_id == "inc_msg_invoice"


def test_same_without_a_candidate_is_forced_new() -> None:
    grounded = ground_link(claim=_claim(), hit=None, draft=_same_draft(), model_version="fake")
    assert grounded.relation is IncidentRelation.NEW_INCIDENT
    assert grounded.candidate_incident_id == "inc_clm_email"
    assert grounded.requires_review is False


def test_conflicting_orders_cannot_stay_same() -> None:
    grounded = ground_link(
        claim=_claim(order_reference="ord_1001"),
        hit=_hit(order_reference="ord_2002", shared_tokens=["right"]),
        draft=_same_draft(),
        model_version="fake",
    )
    assert grounded.relation is IncidentRelation.NEW_INCIDENT
    assert "order_reference" in grounded.contradictory_fields
    assert grounded.candidate_incident_id == "inc_clm_email"


def test_new_incident_opens_its_own_ledger_key() -> None:
    grounded = ground_link(
        claim=_claim(),
        hit=_invoice(),
        draft=LinkDraft(relation=IncidentRelation.NEW_INCIDENT, confidence=0.7),
        model_version="heuristic-v1",
    )
    assert grounded.relation is IncidentRelation.NEW_INCIDENT
    assert grounded.candidate_incident_id == "inc_clm_email"


def test_conflicting_units_become_partial() -> None:
    grounded = ground_link(
        claim=_claim(unit_reference="unit_left"),
        hit=_hit(),
        draft=_same_draft(),
        model_version="fake",
    )
    assert grounded.relation is IncidentRelation.PARTIALLY_OVERLAPPING
    assert "unit_reference" in grounded.contradictory_fields
    assert grounded.requires_review is True


def test_incident_id_comes_from_the_candidate_message_not_the_draft() -> None:
    grounded = ground_link(claim=_claim(), hit=_hit(), draft=_same_draft(), model_version="fake")
    assert grounded.candidate_incident_id == incident_id_for_candidate("msg_wa_001")
    assert grounded.requires_review is False
    assert grounded.relation is IncidentRelation.SAME_INCIDENT


def test_heuristic_links_whatsapp_replacement_as_same() -> None:
    linker = HeuristicIncidentLinker()
    draft = linker.assess(LinkRequest(claim=_claim(), hit=_hit()))
    assert draft.relation is IncidentRelation.SAME_INCIDENT
    grounded = ground_link(claim=_claim(), hit=_hit(), draft=draft, model_version=linker.model_version)
    assert grounded.relation is IncidentRelation.SAME_INCIDENT


def test_heuristic_treats_invoice_as_new() -> None:
    linker = HeuristicIncidentLinker()
    draft = linker.assess(LinkRequest(claim=_claim(), hit=_invoice()))
    assert draft.relation is IncidentRelation.NEW_INCIDENT
