from pydantic import BaseModel, ConfigDict, Field

from app.domain.enums import Channel, Decision, IncidentRelation, RemedyStatus, RemedyType
from app.domain.money import MinorUnits


class HeldOutPrior(BaseModel):
    body: str = Field(min_length=1)
    channel: Channel
    order_reference: str | None = None
    remedy_type: RemedyType | None = None
    status: RemedyStatus | None = None
    amount_minor: MinorUnits | None = None
    consumption_minor: MinorUnits | None = None


class HeldOutIncoming(BaseModel):
    body: str = Field(min_length=1)
    channel: Channel
    order_reference: str | None = None
    amount_minor: MinorUnits
    consumption_minor: MinorUnits | None = None
    remedy_type: RemedyType = RemedyType.CASH_REFUND


class HeldOutExtraOrder(BaseModel):
    order_id: str = Field(min_length=1)
    unit_price_minor: MinorUnits


class HeldOutCase(BaseModel):
    """Frozen end-to-end case. Gold labels were set before looking at model output."""

    model_config = ConfigDict(extra="forbid")

    case_id: str = Field(min_length=1)
    family: str = Field(min_length=1)
    notes: str = Field(min_length=1)
    documented_miss: bool = False
    price_minor: MinorUnits = 499900
    extra_orders: list[HeldOutExtraOrder] = []
    priors: list[HeldOutPrior] = []
    incoming: HeldOutIncoming
    gold_relation: IncidentRelation
    gold_decision: Decision


class HeldOutFile(BaseModel):
    frozen_at: str
    positive_class: str
    cases: list[HeldOutCase]


class CaseOutcome(BaseModel):
    case_id: str
    family: str
    documented_miss: bool
    gold_relation: IncidentRelation
    gold_decision: Decision
    predicted_relation: IncidentRelation
    predicted_decision: Decision
    proposed_minor: int
    relation_match: bool
    decision_match: bool
    prevent_tp: bool
    prevent_fp: bool
    prevent_fn: bool
    unsafe_miss: bool
    notes: str


class MetricReport(BaseModel):
    case_count: int
    prevent_precision: float | None
    prevent_recall: float | None
    same_precision: float | None
    same_recall: float | None
    decision_accuracy: float
    relation_accuracy: float
    false_positive_cost_minor: int
    missed_loss_minor: int
    review_count: int
    documented_miss_ids: list[str]
    documented_miss_confirmed: bool
    intervention_recall: float | None = None
    false_positive_rate: float | None = None
    review_rate: float = 0.0
    automation_coverage: float = 0.0
    prevented_overcompensation_minor: int = 0
    outcomes: list[CaseOutcome]
