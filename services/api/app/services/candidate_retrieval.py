from __future__ import annotations

import re
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import models
from app.domain.enums import Channel, IncidentType, MatchReason, RemedyStatus, RemedyType
from app.schemas.claims import CompiledClaim
from app.schemas.retrieval import ObservedRemedy, RetrievalHit, RetrievalResponse
from app.services.exceptions import ClaimNotFound

_TOKEN = re.compile(r"[a-z0-9]+")
STOPWORDS = frozenset(
    {
        "a",
        "an",
        "and",
        "been",
        "for",
        "from",
        "had",
        "has",
        "have",
        "in",
        "is",
        "it",
        "me",
        "my",
        "of",
        "on",
        "or",
        "please",
        "send",
        "that",
        "the",
        "this",
        "to",
        "was",
        "with",
    }
)

ORDER_MATCH_POINTS = 10
TYPE_MATCH_POINTS = 3
REMEDY_POINTS = 1
MAX_TOKEN_POINTS = 8
DEFAULT_LIMIT = 20
MAX_LIMIT = 50


@dataclass(frozen=True)
class RetrievalCase:
    support_message_id: str
    channel: Channel
    body: str
    occurred_at: datetime
    order_reference: str | None
    incident_type: IncidentType | None
    remedies: tuple[ObservedRemedy, ...]


def tokenize(text: str) -> frozenset[str]:
    return frozenset(token for token in _TOKEN.findall(text.lower()) if token not in STOPWORDS and len(token) > 1)


def score_case(claim: CompiledClaim, case: RetrievalCase) -> RetrievalHit:
    reasons: list[MatchReason] = [MatchReason.SAME_CUSTOMER]
    score = 0
    shared = tokenize(claim.incident_description) & tokenize(case.body)
    if claim.order_reference and case.order_reference and claim.order_reference == case.order_reference:
        score += ORDER_MATCH_POINTS
        reasons.append(MatchReason.ORDER_REFERENCE_MATCH)
    if shared:
        score += min(len(shared), MAX_TOKEN_POINTS)
        reasons.append(MatchReason.SHARED_DESCRIPTION_TOKENS)
    if (
        claim.incident_type is not None
        and case.incident_type is not None
        and claim.incident_type is case.incident_type
    ):
        score += TYPE_MATCH_POINTS
        reasons.append(MatchReason.INCIDENT_TYPE_MATCH)
    if case.remedies:
        score += REMEDY_POINTS
        reasons.append(MatchReason.PRIOR_REMEDY_EXISTS)
    return RetrievalHit(
        candidate_id=case.support_message_id,
        support_message_id=case.support_message_id,
        channel=case.channel,
        body=case.body,
        occurred_at=case.occurred_at,
        order_reference=case.order_reference,
        overlap_score=score,
        match_reasons=reasons,
        shared_tokens=sorted(shared)[:MAX_TOKEN_POINTS],
        remedies=list(case.remedies),
    )


def rank_cases(claim: CompiledClaim, cases: list[RetrievalCase], *, limit: int) -> list[RetrievalHit]:
    hits = [score_case(claim, case) for case in cases]
    hits.sort(key=lambda hit: (-hit.overlap_score, -hit.occurred_at.timestamp()))
    return hits[:limit]


class CandidateRetrieval:
    """Same-customer recall. Does not decide SAME_INCIDENT and does not move money."""

    def __init__(self, session: Session) -> None:
        self.session = session

    def retrieve(self, claim_id: str, *, limit: int = DEFAULT_LIMIT) -> RetrievalResponse:
        capped = min(max(limit, 1), MAX_LIMIT)
        row = self.session.get(models.CompiledClaimRecord, claim_id)
        if row is None:
            raise ClaimNotFound(claim_id)
        claim = CompiledClaim.model_validate(row.payload)
        current = self.session.get(models.SupportMessage, row.support_message_id)
        if current is None:
            raise ClaimNotFound(claim_id)

        messages = self.session.scalars(
            select(models.SupportMessage).where(
                models.SupportMessage.merchant_id == row.merchant_id,
                models.SupportMessage.customer_id == claim.customer_id,
                models.SupportMessage.id != current.id,
                models.SupportMessage.occurred_at < current.occurred_at,
            )
        ).all()
        remedies = self.session.scalars(
            select(models.RemedyRequest).where(
                models.RemedyRequest.merchant_id == row.merchant_id,
                models.RemedyRequest.customer_id == claim.customer_id,
            )
        ).all()
        compiled = self.session.scalars(
            select(models.CompiledClaimRecord).where(
                models.CompiledClaimRecord.merchant_id == row.merchant_id,
                models.CompiledClaimRecord.customer_id == claim.customer_id,
                models.CompiledClaimRecord.id != row.id,
            )
        ).all()

        remedies_by_message: dict[str, list[models.RemedyRequest]] = defaultdict(list)
        for remedy in remedies:
            remedies_by_message[remedy.support_message_id].append(remedy)
        type_by_message: dict[str, IncidentType] = {}
        for other in compiled:
            payload = CompiledClaim.model_validate(other.payload)
            if payload.incident_type is not None:
                type_by_message[other.support_message_id] = payload.incident_type

        cases = [
            RetrievalCase(
                support_message_id=message.id,
                channel=Channel(message.channel),
                body=message.body,
                occurred_at=message.occurred_at,
                order_reference=message.order_reference,
                incident_type=type_by_message.get(message.id),
                remedies=tuple(
                    ObservedRemedy(
                        remedy_request_id=remedy.id,
                        remedy_type=RemedyType(remedy.remedy_type),
                        status=RemedyStatus(remedy.status),
                        amount_minor=remedy.amount_minor,
                        entitlement_consumption_minor=remedy.entitlement_consumption_minor,
                        item_unit_id=remedy.item_unit_id,
                    )
                    for remedy in remedies_by_message[message.id]
                ),
            )
            for message in messages
        ]
        return RetrievalResponse(
            claim_id=claim.claim_id,
            customer_id=claim.customer_id,
            source_support_message_id=current.id,
            hits=rank_cases(claim, cases, limit=capped),
        )
