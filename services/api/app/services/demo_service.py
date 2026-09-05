from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import models
from app.domain.enums import Decision
from app.schemas.audit import AuditEventOut
from app.schemas.demo import DemoRunResponse, DemoScenarioInfo
from app.schemas.ingest import IngestAttemptRequest
from app.schemas.ledger import EntitlementResponse
from app.schemas.world import WorldIngestRequest
from app.services.candidate_retrieval import CandidateRetrieval
from app.services.case_executor import CaseExecutor
from app.services.claim_compiler import ClaimCompiler
from app.services.entitlement_ledger import IncidentNotFound
from app.services.exceptions import IngestError
from app.services.incident_link_service import IncidentLinkService
from app.services.ingest_service import IngestService


class UnknownDemoScenario(IngestError):
    def __init__(self, scenario_id: str) -> None:
        super().__init__(f"unknown demo scenario: {scenario_id}", status_code=404)


def _earbuds_base(tag: str, *, with_history: bool, include_replacement_unit: bool) -> dict:
    """Every identifier is tagged so Allow / Review / Prevent can share one SQLite file."""

    merchant_id = f"mch_demo_{tag}"
    customer_id = f"cus_asha_{tag}"
    order_id = f"ord_{tag}"
    line_id = f"ol_{tag}"
    unit_right = f"unit_right_{tag}"
    unit_left = f"unit_left_{tag}"
    unit_r2 = f"unit_right_r2_{tag}"
    units = [
        {"unit_id": unit_right, "parent_unit_id": None},
        {"unit_id": unit_left, "parent_unit_id": None},
    ]
    if include_replacement_unit:
        units.append({"unit_id": unit_r2, "parent_unit_id": unit_right})
    world = {
        "merchant_id": merchant_id,
        "merchant_name": "Aurum Audio",
        "replace": False,
        "customers": [{"customer_id": customer_id, "display_name": "Asha"}],
        "orders": [
            {
                "order_id": order_id,
                "customer_id": customer_id,
                "created_at": "2026-07-01T10:00:00+05:30",
                "lines": [
                    {
                        "order_line_id": line_id,
                        "product_id": "wireless_earbuds",
                        "product_name": "Wireless Earbuds",
                        "quantity": 1,
                        "unit_price_minor": 499900,
                        "units": units,
                    }
                ],
            }
        ],
        "support_messages": [],
        "historical_remedies": [],
        "razorpay_payments": [
            {
                "razorpay_payment_id": f"pay_test_{tag}",
                "razorpay_order_id": f"order_test_{tag}",
                "internal_order_id": order_id,
                "amount_minor": 499900,
                "status": "captured",
            }
        ],
    }
    if with_history:
        world["support_messages"] = [
            {
                "support_message_id": f"msg_wa_{tag}",
                "customer_id": customer_id,
                "channel": "WHATSAPP",
                "body": "The right earbud has stopped working. Please send a replacement.",
                "occurred_at": "2026-08-10T11:15:00+05:30",
                "order_reference": order_id,
                "external_message_id": f"wa_{tag}",
            }
        ]
        world["historical_remedies"] = [
            {
                "remedy_request_id": f"rrq_repl_{tag}",
                "support_message_id": f"msg_wa_{tag}",
                "customer_id": customer_id,
                "remedy_type": "REPLACEMENT",
                "amount_minor": 499900,
                "entitlement_consumption_minor": 499900,
                "merchant_cost_minor": 220000,
                "currency": "INR",
                "idempotency_key": f"remedy_rrq_repl_{tag}_v1",
                "status": "SETTLED",
                "item_unit_id": unit_right,
            }
        ]
    return world


def _scenario(
    tag: str,
    *,
    title: str,
    expected: Decision,
    summary: str,
    body: str,
    with_history: bool,
    include_replacement_unit: bool,
    named_order: bool,
) -> dict:
    world = _earbuds_base(
        tag,
        with_history=with_history,
        include_replacement_unit=include_replacement_unit,
    )
    customer_id = world["customers"][0]["customer_id"]
    order_id = world["orders"][0]["order_id"]
    return {
        "title": title,
        "expected_decision": expected,
        "summary": summary,
        "world": world,
        "body": body,
        "customer_id": customer_id,
        "order_reference": order_id if named_order else None,
        "key": f"demo_{tag}_refund_v1",
        "external_id": f"demo_{tag}_email",
    }


SCENARIOS: dict[str, dict] = {
    "allow": {
        "title": "Legitimate new incident",
        "expected_decision": Decision.ALLOW,
        "summary": "First contact. She names the right bud. Remaining entitlement covers a full refund.",
        "body": "The right earbud has stopped working. Please refund me.",
        "with_history": False,
        "include_replacement_unit": False,
        "named_order": True,
    },
    "review": {
        "title": "Ambiguous identical units",
        "expected_decision": Decision.REVIEW,
        "summary": "Two buds in the order. The email does not say which one failed. Do not guess.",
        "body": "One of the earbuds has failed. Please refund me.",
        "with_history": False,
        "include_replacement_unit": False,
        "named_order": True,
    },
    "prevent": {
        "title": "Prevent duplicate compensation",
        "expected_decision": Decision.PREVENT_DUPLICATE,
        "summary": "WhatsApp replacement already settled. Email asks for cash for the same defect.",
        "body": "The right side produces no audio. Please refund me.",
        "with_history": True,
        "include_replacement_unit": True,
        "named_order": False,
    },
}


class DemoService:
    def __init__(
        self,
        session: Session,
        ingest: IngestService,
        compiler: ClaimCompiler,
        retrieval: CandidateRetrieval,
        links: IncidentLinkService,
        executor: CaseExecutor,
    ) -> None:
        self.session = session
        self.ingest = ingest
        self.compiler = compiler
        self.retrieval = retrieval
        self.links = links
        self.executor = executor

    def list_scenarios(self) -> list[DemoScenarioInfo]:
        return [
            DemoScenarioInfo(
                scenario_id=scenario_id,
                title=spec["title"],
                expected_decision=spec["expected_decision"],
                summary=spec["summary"],
            )
            for scenario_id, spec in SCENARIOS.items()
        ]

    def run(self, scenario_id: str) -> DemoRunResponse:
        spec = SCENARIOS.get(scenario_id)
        if spec is None:
            raise UnknownDemoScenario(scenario_id)
        tag = f"{scenario_id}_{uuid4().hex[:8]}"
        built = _scenario(
            tag,
            title=spec["title"],
            expected=spec["expected_decision"],
            summary=spec["summary"],
            body=spec["body"],
            with_history=spec["with_history"],
            include_replacement_unit=spec["include_replacement_unit"],
            named_order=spec["named_order"],
        )
        world = built["world"]
        ingested_world = self.ingest.ingest_world(WorldIngestRequest.model_validate(world))
        attempt = self.ingest.ingest_attempt(
            IngestAttemptRequest.model_validate(
                {
                    "message": {
                        "merchant_id": world["merchant_id"],
                        "customer_id": built["customer_id"],
                        "channel": "EMAIL",
                        "body": built["body"],
                        "occurred_at": datetime(2026, 8, 20, 9, 0, tzinfo=timezone.utc).isoformat(),
                        "order_reference": built["order_reference"],
                        "external_message_id": built["external_id"],
                    },
                    "proposal": {
                        "remedy_type": "CASH_REFUND",
                        "amount_minor": 499900,
                        "entitlement_consumption_minor": 499900,
                        "currency": "INR",
                        "idempotency_key": built["key"],
                    },
                }
            )
        )
        compiled = self.compiler.compile_message(attempt.support_message_id)
        retrieval = self.retrieval.retrieve(compiled.claim.claim_id)
        link = self.links.link_claim(compiled.claim.claim_id)
        execution = self.executor.execute(compiled.claim.claim_id)
        ledger = None
        try:
            position = self.executor.evaluator.ledger.get_position(
                world["merchant_id"], execution.evaluation.incident_id
            )
            ledger = EntitlementResponse(
                incident_id=position.incident_id,
                allowed_entitlement_minor=position.allowed_entitlement_minor,
                settled_entitlement_minor=position.settled_entitlement_minor,
                reserved_entitlement_minor=position.reserved_entitlement_minor,
                remaining_minor=position.remaining_minor(),
            )
        except IncidentNotFound:
            ledger = None
        events = list(
            self.session.scalars(
                select(models.AuditEvent)
                .where(models.AuditEvent.merchant_id == world["merchant_id"])
                .order_by(models.AuditEvent.created_at.asc())
            ).all()
        )
        return DemoRunResponse(
            scenario_id=scenario_id,
            title=spec["title"],
            expected_decision=spec["expected_decision"],
            merchant_id=ingested_world.merchant_id,
            customer_id=built["customer_id"],
            support_message_id=attempt.support_message_id,
            claim=compiled.claim,
            retrieval=retrieval,
            link=link,
            execution=execution,
            ledger=ledger,
            audit=[AuditEventOut.model_validate(row) for row in events],
            channel="EMAIL",
            message_body=spec["body"],
        )
