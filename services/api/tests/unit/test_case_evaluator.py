from app.domain.enums import Decision, IncidentRelation, ReasonCode, RemedyStatus
from app.schemas.incidents import EntitlementPosition
from app.services.case_evaluator import historical_settled_minor
from app.services.policy_engine import decide


class _Remedy:
    def __init__(self, status: str, amount: int) -> None:
        self.status = status
        self.entitlement_consumption_minor = amount


def test_historical_settled_ignores_proposed() -> None:
    rows = [
        _Remedy(RemedyStatus.SETTLED.value, 499900),
        _Remedy(RemedyStatus.PROPOSED.value, 499900),
    ]
    assert historical_settled_minor(rows) == 499900  # type: ignore[arg-type]


def test_naive_open_without_history_would_allow_the_email_refund() -> None:
    allowed = 499900
    proposed = 499900
    history = [_Remedy(RemedyStatus.SETTLED.value, 499900)]
    naive_settled = 0
    correct_settled = historical_settled_minor(history)  # type: ignore[arg-type]
    naive = decide(
        EntitlementPosition(
            incident_id="inc_msg_wa_001",
            allowed_entitlement_minor=allowed,
            settled_entitlement_minor=naive_settled,
            reserved_entitlement_minor=0,
        ),
        IncidentRelation.SAME_INCIDENT,
        proposed,
    )
    correct = decide(
        EntitlementPosition(
            incident_id="inc_msg_wa_001",
            allowed_entitlement_minor=allowed,
            settled_entitlement_minor=correct_settled,
            reserved_entitlement_minor=0,
        ),
        IncidentRelation.SAME_INCIDENT,
        proposed,
    )
    assert naive.decision is Decision.ALLOW
    assert correct.decision is Decision.PREVENT_DUPLICATE
    assert ReasonCode.ENTITLEMENT_EXHAUSTED in correct.reason_codes
    assert correct.avoidable_overcompensation_minor == 499900
