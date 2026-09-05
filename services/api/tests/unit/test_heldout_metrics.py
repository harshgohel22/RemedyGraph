from app.domain.enums import Decision, IncidentRelation
from app.evaluation.metrics import score_case, summarize
from app.evaluation.schema import HeldOutCase, HeldOutIncoming


def _case(
    case_id: str,
    gold_relation: IncidentRelation,
    gold_decision: Decision,
    *,
    documented_miss: bool = False,
    amount_minor: int = 100,
) -> HeldOutCase:
    return HeldOutCase(
        case_id=case_id,
        family="unit",
        notes="unit metric case",
        documented_miss=documented_miss,
        incoming=HeldOutIncoming(
            body="refund me",
            channel="EMAIL",
            amount_minor=amount_minor,
        ),
        gold_relation=gold_relation,
        gold_decision=gold_decision,
    )


def test_prevent_precision_and_false_positive_cost() -> None:
    outcomes = [
        score_case(
            _case("tp", IncidentRelation.SAME_INCIDENT, Decision.PREVENT_DUPLICATE, amount_minor=400),
            IncidentRelation.SAME_INCIDENT,
            Decision.PREVENT_DUPLICATE,
        ),
        score_case(
            _case("fp", IncidentRelation.NEW_INCIDENT, Decision.ALLOW, amount_minor=250),
            IncidentRelation.SAME_INCIDENT,
            Decision.PREVENT_DUPLICATE,
        ),
    ]
    report = summarize(outcomes)
    assert report.prevent_precision == 0.5
    assert report.false_positive_cost_minor == 250
    assert report.missed_loss_minor == 0


def test_unsafe_miss_costs_the_proposed_amount() -> None:
    outcomes = [
        score_case(
            _case(
                "miss",
                IncidentRelation.SAME_INCIDENT,
                Decision.PREVENT_DUPLICATE,
                documented_miss=True,
                amount_minor=499900,
            ),
            IncidentRelation.NEW_INCIDENT,
            Decision.ALLOW,
        )
    ]
    report = summarize(outcomes)
    assert report.prevent_recall == 0.0
    assert report.missed_loss_minor == 499900
    assert report.documented_miss_confirmed is True
    assert outcomes[0].unsafe_miss is True


def test_review_on_gold_prevent_is_a_confirmed_safe_miss() -> None:
    outcomes = [
        score_case(
            _case(
                "safe",
                IncidentRelation.SAME_INCIDENT,
                Decision.PREVENT_DUPLICATE,
                documented_miss=True,
                amount_minor=499900,
            ),
            IncidentRelation.NEW_INCIDENT,
            Decision.REVIEW,
        )
    ]
    report = summarize(outcomes)
    assert outcomes[0].unsafe_miss is False
    assert outcomes[0].prevent_fn is True
    assert report.missed_loss_minor == 0
    assert report.documented_miss_confirmed is True
