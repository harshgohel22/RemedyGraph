from app.domain.enums import Decision, IncidentRelation, ReasonCode
from app.domain.ids import new_id
from app.schemas.decisions import PolicyDecision
from app.schemas.incidents import EntitlementPosition


class PolicyInvariantError(ValueError):
    """Ledger numbers that already violate settled + reserved <= allowed."""


def decide(
    position: EntitlementPosition,
    relation: IncidentRelation,
    proposed_consumption_minor: int,
    *,
    requires_review: bool = False,
    contradictory_fields: list[str] | None = None,
    semantic_confidence: float | None = None,
) -> PolicyDecision:
    """Deterministic policy. No I/O. No LLM. Relation is an input, not computed here."""
    contradictions = contradictory_fields or []
    remaining_before = _remaining(position)

    # A NEW label may carry the identifier clash that proved it is new. That is not a review trigger.
    if requires_review or (contradictions and relation is not IncidentRelation.NEW_INCIDENT):
        return _result(
            position,
            relation,
            proposed_consumption_minor,
            remaining_before,
            Decision.REVIEW,
            _review_reasons(relation, requires_review, contradictions),
            consume=False,
            semantic_confidence=semantic_confidence,
        )

    if relation in {IncidentRelation.UNCERTAIN, IncidentRelation.PARTIALLY_OVERLAPPING}:
        reasons = (
            [ReasonCode.UNCERTAIN_LINK]
            if relation is IncidentRelation.UNCERTAIN
            else [ReasonCode.PARTIALLY_OVERLAPPING]
        )
        return _result(
            position,
            relation,
            proposed_consumption_minor,
            remaining_before,
            Decision.REVIEW,
            reasons,
            consume=False,
            semantic_confidence=semantic_confidence,
        )

    exceeds = proposed_consumption_minor > remaining_before

    if relation is IncidentRelation.NEW_INCIDENT and exceeds:
        # Likely a bad extraction (asked for more than the unit's policy cap), not a proven duplicate.
        return _result(
            position,
            relation,
            proposed_consumption_minor,
            remaining_before,
            Decision.REVIEW,
            [ReasonCode.NEW_INCIDENT, ReasonCode.ENTITLEMENT_EXCEEDED],
            consume=False,
            semantic_confidence=semantic_confidence,
        )

    if relation is IncidentRelation.SAME_INCIDENT and exceeds:
        reasons = [ReasonCode.SAME_INCIDENT]
        if remaining_before == 0:
            reasons.append(ReasonCode.ENTITLEMENT_EXHAUSTED)
            if position.reserved_entitlement_minor > 0:
                reasons.append(ReasonCode.RESERVATION_HELD)
        else:
            reasons.append(ReasonCode.ENTITLEMENT_EXCEEDED)
        return _result(
            position,
            relation,
            proposed_consumption_minor,
            remaining_before,
            Decision.PREVENT_DUPLICATE,
            reasons,
            consume=False,
            semantic_confidence=semantic_confidence,
        )

    if relation in {IncidentRelation.SAME_INCIDENT, IncidentRelation.NEW_INCIDENT} and not exceeds:
        relation_code = (
            ReasonCode.NEW_INCIDENT if relation is IncidentRelation.NEW_INCIDENT else ReasonCode.SAME_INCIDENT
        )
        return _result(
            position,
            relation,
            proposed_consumption_minor,
            remaining_before,
            Decision.ALLOW,
            [relation_code, ReasonCode.ENTITLEMENT_AVAILABLE],
            consume=True,
            semantic_confidence=semantic_confidence,
        )

    return _result(
        position,
        relation,
        proposed_consumption_minor,
        remaining_before,
        Decision.REVIEW,
        [ReasonCode.REVIEW_REQUIRED],
        consume=False,
        semantic_confidence=semantic_confidence,
    )


def _remaining(position: EntitlementPosition) -> int:
    remaining = position.remaining_minor()
    if remaining < 0:
        raise PolicyInvariantError(
            "settled + reserved exceed allowed entitlement; ledger is already inconsistent"
        )
    return remaining


def _review_reasons(
    relation: IncidentRelation,
    requires_review: bool,
    contradictions: list[str],
) -> list[ReasonCode]:
    reasons: list[ReasonCode] = []
    if contradictions:
        reasons.append(ReasonCode.CONTRADICTION)
    if requires_review:
        reasons.append(ReasonCode.REVIEW_REQUIRED)
    if relation is IncidentRelation.UNCERTAIN:
        reasons.append(ReasonCode.UNCERTAIN_LINK)
    if relation is IncidentRelation.PARTIALLY_OVERLAPPING:
        reasons.append(ReasonCode.PARTIALLY_OVERLAPPING)
    if not reasons:
        reasons.append(ReasonCode.REVIEW_REQUIRED)
    return reasons


def _result(
    position: EntitlementPosition,
    relation: IncidentRelation,
    proposed: int,
    remaining_before: int,
    decision: Decision,
    reason_codes: list[ReasonCode],
    *,
    consume: bool,
    semantic_confidence: float | None,
) -> PolicyDecision:
    remaining_after = remaining_before - proposed if consume else remaining_before
    avoidable = 0
    if decision is Decision.PREVENT_DUPLICATE:
        avoidable = max(0, proposed - remaining_before)
    return PolicyDecision(
        decision_id=new_id("dec"),
        decision=decision,
        reason_codes=reason_codes,
        incident_id=position.incident_id,
        allowed_entitlement_minor=position.allowed_entitlement_minor,
        settled_entitlement_minor=position.settled_entitlement_minor,
        reserved_entitlement_minor=position.reserved_entitlement_minor,
        remaining_before_minor=remaining_before,
        proposed_consumption_minor=proposed,
        remaining_after_minor=remaining_after,
        avoidable_overcompensation_minor=avoidable,
        max_safe_amount_minor=remaining_before,
        semantic_confidence=semantic_confidence,
        audit_id=None,
    )
