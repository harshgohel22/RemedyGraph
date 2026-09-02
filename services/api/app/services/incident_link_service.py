from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import models
from app.domain.enums import AuditEventType, IncidentRelation
from app.domain.ids import new_id
from app.schemas.claims import CompiledClaim
from app.schemas.incidents import IncidentLinkAssessment, LinkClaimResponse
from app.schemas.retrieval import RetrievalHit
from app.services.candidate_retrieval import CandidateRetrieval
from app.services.exceptions import ClaimNotFound, LinkNotFound
from app.services.incident_link_grounding import ground_link, incident_id_for_candidate
from app.services.incident_linker import IncidentLinker, LinkRequest

_RELATION_RANK = {
    IncidentRelation.SAME_INCIDENT: 0,
    IncidentRelation.PARTIALLY_OVERLAPPING: 1,
    IncidentRelation.UNCERTAIN: 2,
    IncidentRelation.NEW_INCIDENT: 3,
}


class IncidentLinkService:
    def __init__(self, session: Session, linker: IncidentLinker, retrieval: CandidateRetrieval) -> None:
        self.session = session
        self.linker = linker
        self.retrieval = retrieval

    def link_claim(self, claim_id: str) -> LinkClaimResponse:
        existing = self._rows(claim_id)
        if existing:
            return self._response(existing, replayed=True, audit_event=AuditEventType.INCIDENT_LINK_REPLAYED)

        row = self.session.get(models.CompiledClaimRecord, claim_id)
        if row is None:
            raise ClaimNotFound(claim_id)
        claim = CompiledClaim.model_validate(row.payload)
        hits = self.retrieval.retrieve(claim_id).hits
        if not hits:
            assessments = [self._assess(claim, None)]
        else:
            assessments = [self._assess(claim, hit) for hit in hits]
        primary = _select_primary(assessments, hits)
        stored: list[models.IncidentLinkRecord] = []
        for assessment in assessments:
            stored.append(
                models.IncidentLinkRecord(
                    id=new_id("lnk"),
                    merchant_id=row.merchant_id,
                    claim_id=claim.claim_id,
                    candidate_incident_id=assessment.candidate_incident_id,
                    is_primary=assessment.candidate_incident_id == primary.candidate_incident_id,
                    payload=assessment.model_dump(mode="json"),
                )
            )
            self.session.add(stored[-1])
        self.session.flush()
        return self._response(stored, replayed=False, audit_event=AuditEventType.INCIDENT_LINKED)

    def get_link(self, claim_id: str) -> LinkClaimResponse:
        existing = self._rows(claim_id)
        if not existing:
            if self.session.get(models.CompiledClaimRecord, claim_id) is None:
                raise ClaimNotFound(claim_id)
            raise LinkNotFound(claim_id)
        return self._response(existing, replayed=True, audit_event=None)

    def _assess(self, claim: CompiledClaim, hit: RetrievalHit | None) -> IncidentLinkAssessment:
        return ground_link(
            claim=claim,
            hit=hit,
            draft=self.linker.assess(LinkRequest(claim=claim, hit=hit)),
            model_version=self.linker.model_version,
        )

    def _rows(self, claim_id: str) -> list[models.IncidentLinkRecord]:
        return list(
            self.session.scalars(
                select(models.IncidentLinkRecord).where(models.IncidentLinkRecord.claim_id == claim_id)
            ).all()
        )

    def _response(
        self,
        rows: list[models.IncidentLinkRecord],
        *,
        replayed: bool,
        audit_event: AuditEventType | None,
    ) -> LinkClaimResponse:
        assessments = [IncidentLinkAssessment.model_validate(row.payload) for row in rows]
        primary_row = next((row for row in rows if row.is_primary), rows[0])
        primary = IncidentLinkAssessment.model_validate(primary_row.payload)
        audit_id = None
        if audit_event is not None:
            audit_id = self._audit(
                primary_row,
                audit_event,
                {
                    "claim_id": primary.claim_id,
                    "primary_relation": primary.relation.value,
                    "primary_incident_id": primary.candidate_incident_id,
                },
            )
        return LinkClaimResponse(
            primary=primary,
            assessments=assessments,
            replayed=replayed,
            audit_id=audit_id,
        )

    def _audit(
        self,
        row: models.IncidentLinkRecord,
        event_type: AuditEventType,
        payload: dict,
    ) -> str:
        audit_id = new_id("aud")
        self.session.add(
            models.AuditEvent(
                id=audit_id,
                merchant_id=row.merchant_id,
                event_type=event_type.value,
                payload=payload,
            )
        )
        self.session.flush()
        return audit_id


def _select_primary(
    assessments: list[IncidentLinkAssessment],
    hits: list[RetrievalHit],
) -> IncidentLinkAssessment:
    overlap = {incident_id_for_candidate(hit.support_message_id): hit.overlap_score for hit in hits}
    return min(
        assessments,
        key=lambda item: (
            _RELATION_RANK[item.relation],
            -overlap.get(item.candidate_incident_id, 0),
        ),
    )
