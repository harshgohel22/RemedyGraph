from datetime import datetime

from pydantic import BaseModel, Field

from app.domain.enums import Channel, MatchReason, RemedyStatus, RemedyType
from app.domain.money import MinorUnits


class ObservedRemedy(BaseModel):
    """History attached to a candidate case. Not an entitlement decision."""

    remedy_request_id: str = Field(min_length=1)
    remedy_type: RemedyType
    status: RemedyStatus
    amount_minor: MinorUnits
    entitlement_consumption_minor: MinorUnits
    item_unit_id: str | None = None


class RetrievalHit(BaseModel):
    """A prior case the linker may compare. overlap_score is rank only, not SAME/NEW."""

    candidate_id: str = Field(min_length=1)
    support_message_id: str = Field(min_length=1)
    channel: Channel
    body: str = Field(min_length=1)
    occurred_at: datetime
    order_reference: str | None = None
    overlap_score: int = Field(ge=0)
    match_reasons: list[MatchReason]
    shared_tokens: list[str] = []
    remedies: list[ObservedRemedy] = []


class RetrievalResponse(BaseModel):
    claim_id: str
    customer_id: str
    source_support_message_id: str
    hits: list[RetrievalHit]
