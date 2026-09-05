from sqlalchemy import select
from sqlalchemy.orm import Session

import re

from app.db import models
from app.domain.enums import AuditEventType, Decision, ReasonCode, RemedyStatus
from app.domain.ids import new_id
from app.schemas.claims import CompiledClaim
from app.schemas.decisions import CaseEvaluationResponse, PolicyDecision
from app.schemas.incidents import EntitlementPosition
from app.services.exceptions import (
    AttemptAlreadySettled,
    AttemptNotFound,
    ClaimNotFound,
    EntitlementCapUnknown,
)
from app.services.incident_link_grounding import source_id_from_incident
from app.services.incident_link_service import IncidentLinkService
from app.services.ledger_service import LedgerService
from app.services.policy_engine import decide


_UNIT_HINT = re.compile(r"\b(left|right)\b", re.IGNORECASE)


def historical_settled_minor(remedies: list[models.RemedyRequest]) -> int:
    """Sum SETTLED consumption. PROPOSED attempts are not money yet."""

    return sum(
        remedy.entitlement_consumption_minor
        for remedy in remedies
        if remedy.status == RemedyStatus.SETTLED.value
    )


class CaseEvaluator:
    """Deterministic money gate after linkage. Does not reserve or call Razorpay."""

    def __init__(self, session: Session, links: IncidentLinkService, ledger: LedgerService) -> None:
        self.session = session
        self.links = links
        self.ledger = ledger

    def evaluate(self, claim_id: str) -> CaseEvaluationResponse:
        record = self.session.get(models.CompiledClaimRecord, claim_id)
        if record is None:
            raise ClaimNotFound(claim_id)
        claim = CompiledClaim.model_validate(record.payload)
        linked = self.links.link_claim(claim_id)
        primary = linked.primary
        current = self._current_attempt(record.support_message_id)
        if current.status == RemedyStatus.SETTLED.value:
            raise AttemptAlreadySettled(current.id)

        history = self._history_for_incident(record.merchant_id, primary.candidate_incident_id)
        try:
            allowed = self._allowed_minor(
                record.merchant_id,
                claim.customer_id,
                order_ids=self._order_ids(claim, record.support_message_id, history),
            )
        except EntitlementCapUnknown:
            position = EntitlementPosition(
                incident_id=primary.candidate_incident_id,
                allowed_entitlement_minor=0,
                settled_entitlement_minor=0,
                reserved_entitlement_minor=0,
            )
            decision = decide(
                position,
                primary.relation,
                current.entitlement_consumption_minor,
                requires_review=True,
                contradictory_fields=primary.contradictory_fields,
                semantic_confidence=primary.confidence,
            )
            reasons = list(decision.reason_codes)
            if ReasonCode.ENTITLEMENT_CAP_UNKNOWN not in reasons:
                reasons.append(ReasonCode.ENTITLEMENT_CAP_UNKNOWN)
            decision = decision.model_copy(update={"reason_codes": reasons})
            if decision.decision is Decision.REVIEW:
                current.status = RemedyStatus.REVIEW_REQUIRED.value
            self.session.flush()
            decision = decision.model_copy(
                update={
                    "audit_id": self._audit(
                        record.merchant_id,
                        current.id,
                        {
                            "claim_id": claim.claim_id,
                            "incident_id": primary.candidate_incident_id,
                            "decision": decision.decision.value,
                            "remaining_minor": 0,
                            "cap_unknown": True,
                        },
                    )
                }
            )
            return CaseEvaluationResponse(
                claim_id=claim.claim_id,
                remedy_request_id=current.id,
                incident_id=primary.candidate_incident_id,
                remaining_minor=0,
                decision=decision,
                link=primary,
            )

        settled_seed = historical_settled_minor(history)
        position = self.ledger.ensure_incident(
            record.merchant_id,
            primary.candidate_incident_id,
            allowed,
            settled_seed,
        )
        self._attach_incident(current, history, primary.candidate_incident_id)
        order_ids = self._order_ids(claim, record.support_message_id, history)
        unit_ambiguous = self._unit_requires_review(claim, order_ids)
        decision = decide(
            position,
            primary.relation,
            current.entitlement_consumption_minor,
            requires_review=primary.requires_review or unit_ambiguous,
            contradictory_fields=primary.contradictory_fields,
            semantic_confidence=primary.confidence,
        )
        if unit_ambiguous:
            reasons = list(decision.reason_codes)
            if ReasonCode.UNIT_AMBIGUOUS not in reasons:
                reasons.append(ReasonCode.UNIT_AMBIGUOUS)
            decision = decision.model_copy(update={"reason_codes": reasons})
        if decision.decision is Decision.REVIEW:
            current.status = RemedyStatus.REVIEW_REQUIRED.value
        self.session.flush()
        decision = decision.model_copy(
            update={
                "audit_id": self._audit(
                    record.merchant_id,
                    current.id,
                    {
                        "claim_id": claim.claim_id,
                        "incident_id": primary.candidate_incident_id,
                        "decision": decision.decision.value,
                        "remaining_minor": position.remaining_minor(),
                    },
                )
            }
        )
        return CaseEvaluationResponse(
            claim_id=claim.claim_id,
            remedy_request_id=current.id,
            incident_id=primary.candidate_incident_id,
            remaining_minor=position.remaining_minor(),
            decision=decision,
            link=primary,
        )

    def _current_attempt(self, support_message_id: str) -> models.RemedyRequest:
        remedies = list(
            self.session.scalars(
                select(models.RemedyRequest).where(
                    models.RemedyRequest.support_message_id == support_message_id
                )
            ).all()
        )
        if not remedies:
            raise AttemptNotFound(support_message_id)
        proposed = [row for row in remedies if row.status == RemedyStatus.PROPOSED.value]
        if proposed:
            return proposed[0]
        return remedies[0]

    def _history_for_incident(
        self, merchant_id: str, incident_id: str
    ) -> list[models.RemedyRequest]:
        source_id = source_id_from_incident(incident_id)
        message = self.session.get(models.SupportMessage, source_id)
        if message is None or message.merchant_id != merchant_id:
            return []
        return list(
            self.session.scalars(
                select(models.RemedyRequest).where(
                    models.RemedyRequest.merchant_id == merchant_id,
                    models.RemedyRequest.support_message_id == message.id,
                )
            ).all()
        )

    def _order_ids(
        self,
        claim: CompiledClaim,
        current_message_id: str,
        history: list[models.RemedyRequest],
    ) -> set[str]:
        ids: set[str] = set()
        if claim.order_reference:
            ids.add(claim.order_reference)
        current = self.session.get(models.SupportMessage, current_message_id)
        if current is not None and current.order_reference:
            ids.add(current.order_reference)
        for remedy in history:
            message = self.session.get(models.SupportMessage, remedy.support_message_id)
            if message is not None and message.order_reference:
                ids.add(message.order_reference)
        return ids

    def _allowed_minor(self, merchant_id: str, customer_id: str, order_ids: set[str]) -> int:
        prices: list[int] = []
        for order_id in order_ids:
            order = self.session.get(models.Order, order_id)
            if order is None or order.merchant_id != merchant_id or order.customer_id != customer_id:
                continue
            for line in order.lines:
                prices.append(line.unit_price_minor)
        if not prices:
            raise EntitlementCapUnknown()
        return max(prices)

    def _unit_requires_review(self, claim: CompiledClaim, order_ids: set[str]) -> bool:
        """Two sibling units and no left/right hint: do not guess which one failed."""

        if claim.unit_reference:
            return False
        if _UNIT_HINT.search(claim.incident_description or ""):
            return False
        count = 0
        for order_id in order_ids:
            order = self.session.get(models.Order, order_id)
            if order is None:
                continue
            for line in order.lines:
                count += len(line.units)
        return count > 1

    def _attach_incident(
        self,
        current: models.RemedyRequest,
        history: list[models.RemedyRequest],
        incident_id: str,
    ) -> None:
        if current.incident_id is None:
            current.incident_id = incident_id
        for remedy in history:
            if remedy.incident_id is None:
                remedy.incident_id = incident_id

    def _audit(self, merchant_id: str, remedy_request_id: str, payload: dict) -> str:
        audit_id = new_id("aud")
        self.session.add(
            models.AuditEvent(
                id=audit_id,
                merchant_id=merchant_id,
                event_type=AuditEventType.POLICY_EVALUATED.value,
                remedy_request_id=remedy_request_id,
                payload=payload,
            )
        )
        self.session.flush()
        return audit_id
