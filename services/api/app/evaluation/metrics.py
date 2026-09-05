from app.domain.enums import Decision, IncidentRelation
from app.evaluation.schema import CaseOutcome, HeldOutCase, MetricReport


def _ratio(numerator: int, denominator: int) -> float | None:
    if denominator == 0:
        return None
    return numerator / denominator


def score_case(
    case: HeldOutCase,
    predicted_relation: IncidentRelation,
    predicted_decision: Decision,
) -> CaseOutcome:
    """Compare one frozen label to one live prediction. No learning happens here."""

    proposed = case.incoming.consumption_minor or case.incoming.amount_minor
    gold_prevent = case.gold_decision is Decision.PREVENT_DUPLICATE
    pred_prevent = predicted_decision is Decision.PREVENT_DUPLICATE
    return CaseOutcome(
        case_id=case.case_id,
        family=case.family,
        documented_miss=case.documented_miss,
        gold_relation=case.gold_relation,
        gold_decision=case.gold_decision,
        predicted_relation=predicted_relation,
        predicted_decision=predicted_decision,
        proposed_minor=proposed,
        relation_match=predicted_relation is case.gold_relation,
        decision_match=predicted_decision is case.gold_decision,
        prevent_tp=gold_prevent and pred_prevent,
        prevent_fp=pred_prevent and case.gold_decision is Decision.ALLOW,
        prevent_fn=gold_prevent and not pred_prevent,
        unsafe_miss=gold_prevent and predicted_decision is Decision.ALLOW,
        notes=case.notes,
    )


def summarize(outcomes: list[CaseOutcome]) -> MetricReport:
    tp = sum(1 for row in outcomes if row.prevent_tp)
    fp = sum(1 for row in outcomes if row.prevent_fp)
    fn = sum(1 for row in outcomes if row.prevent_fn)
    same_tp = sum(
        1
        for row in outcomes
        if row.gold_relation is IncidentRelation.SAME_INCIDENT
        and row.predicted_relation is IncidentRelation.SAME_INCIDENT
    )
    same_fp = sum(
        1
        for row in outcomes
        if row.predicted_relation is IncidentRelation.SAME_INCIDENT
        and row.gold_relation is not IncidentRelation.SAME_INCIDENT
    )
    same_fn = sum(
        1
        for row in outcomes
        if row.gold_relation is IncidentRelation.SAME_INCIDENT
        and row.predicted_relation is not IncidentRelation.SAME_INCIDENT
    )
    documented = [row.case_id for row in outcomes if row.documented_miss]
    return MetricReport(
        case_count=len(outcomes),
        prevent_precision=_ratio(tp, tp + fp),
        prevent_recall=_ratio(tp, tp + fn),
        same_precision=_ratio(same_tp, same_tp + same_fp),
        same_recall=_ratio(same_tp, same_tp + same_fn),
        decision_accuracy=_ratio(sum(1 for row in outcomes if row.decision_match), len(outcomes)) or 0.0,
        relation_accuracy=_ratio(sum(1 for row in outcomes if row.relation_match), len(outcomes)) or 0.0,
        false_positive_cost_minor=sum(row.proposed_minor for row in outcomes if row.prevent_fp),
        missed_loss_minor=sum(row.proposed_minor for row in outcomes if row.unsafe_miss),
        review_count=sum(1 for row in outcomes if row.predicted_decision is Decision.REVIEW),
        documented_miss_ids=documented,
        documented_miss_confirmed=any(
            row.documented_miss and (row.prevent_fn or row.unsafe_miss) for row in outcomes
        ),
        outcomes=outcomes,
    )
