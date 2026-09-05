from app.domain.enums import IncidentRelation
from app.schemas.claims import CompiledClaim
from app.schemas.incidents import IncidentLinkAssessment, LinkDraft
from app.schemas.retrieval import RetrievalHit


def incident_id_for_candidate(support_message_id: str) -> str:
    return f"inc_{support_message_id}"


def incident_id_for_new_claim(claim_id: str) -> str:
    return f"inc_{claim_id}"


def source_id_from_incident(incident_id: str) -> str:
    prefix = "inc_"
    if incident_id.startswith(prefix):
        return incident_id[len(prefix) :]
    return incident_id


def ground_link(
    *,
    claim: CompiledClaim,
    hit: RetrievalHit | None,
    draft: LinkDraft,
    model_version: str | None,
) -> IncidentLinkAssessment:
    """Keep language evidence. Downgrade unsafe SAME. Never mint ids from the draft."""

    if hit is None:
        return IncidentLinkAssessment(
            claim_id=claim.claim_id,
            candidate_incident_id=incident_id_for_new_claim(claim.claim_id),
            relation=IncidentRelation.NEW_INCIDENT,
            confidence=1.0,
            evidence_for=["no prior cases for this customer"],
            evidence_against=[],
            contradictory_fields=[],
            requires_review=False,
            model_version=model_version,
        )

    relation = draft.relation
    confidence = draft.confidence
    evidence_for = list(draft.evidence_for)
    evidence_against = list(draft.evidence_against)
    contradictions = list(draft.contradictory_fields)
    requires_review = draft.requires_review
    incident_id = incident_id_for_candidate(hit.support_message_id)

    order_match = bool(
        claim.order_reference and hit.order_reference and claim.order_reference == hit.order_reference
    )
    orders_conflict = bool(
        claim.order_reference and hit.order_reference and claim.order_reference != hit.order_reference
    )
    hit_units = {remedy.item_unit_id for remedy in hit.remedies if remedy.item_unit_id}
    units_conflict = bool(claim.unit_reference and hit_units and claim.unit_reference not in hit_units)

    if orders_conflict:
        _add(contradictions, "order_reference")
        _add(evidence_against, "attested order ids differ")
        if relation is IncidentRelation.SAME_INCIDENT:
            relation = IncidentRelation.NEW_INCIDENT
            confidence = min(confidence, 0.6)

    if units_conflict:
        _add(contradictions, "unit_reference")
        _add(evidence_against, "attested unit ids differ")
        if relation is IncidentRelation.SAME_INCIDENT:
            relation = IncidentRelation.PARTIALLY_OVERLAPPING
            confidence = min(confidence, 0.6)

    weak_same = relation is IncidentRelation.SAME_INCIDENT and not order_match and not hit.shared_tokens
    if weak_same:
        relation = IncidentRelation.UNCERTAIN
        confidence = min(confidence, 0.4)
        _add(evidence_against, "SAME proposed without shared tokens or order match")

    if contradictions and relation is IncidentRelation.SAME_INCIDENT:
        relation = IncidentRelation.UNCERTAIN
        _add(evidence_against, "SAME proposed despite contradictory identifiers")

    if relation in {IncidentRelation.UNCERTAIN, IncidentRelation.PARTIALLY_OVERLAPPING}:
        requires_review = True
    if relation is IncidentRelation.SAME_INCIDENT:
        requires_review = False
    if relation is IncidentRelation.NEW_INCIDENT:
        incident_id = incident_id_for_new_claim(claim.claim_id)

    return IncidentLinkAssessment(
        claim_id=claim.claim_id,
        candidate_incident_id=incident_id,
        relation=relation,
        confidence=confidence,
        evidence_for=evidence_for,
        evidence_against=evidence_against,
        contradictory_fields=contradictions,
        requires_review=requires_review,
        model_version=model_version,
    )


def _add(fields: list[str], value: str) -> None:
    if value not in fields:
        fields.append(value)
