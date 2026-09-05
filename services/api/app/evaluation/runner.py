from __future__ import annotations

import json
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy.orm import sessionmaker

from app.api.deps import get_razorpay_gateway
from app.db.base import Base
from app.db.session import create_db_engine, get_db
from app.domain.enums import Decision, IncidentRelation
from app.evaluation.metrics import score_case, summarize
from app.evaluation.schema import HeldOutCase, HeldOutFile, MetricReport
from app.evaluation.worlds import expand_attempt, expand_world
from app.main import create_app
from app.services.razorpay_client import FakeRazorpayGateway

FIXTURES = Path(__file__).resolve().parents[2] / "tests" / "fixtures"
HELDOUT_PATH = FIXTURES / "heldout_cases.json"


@contextmanager
def eval_client() -> Iterator[TestClient]:
    engine = create_db_engine("sqlite://", static_memory=True)
    TestingSessionLocal = sessionmaker(
        bind=engine,
        autoflush=False,
        autocommit=False,
        expire_on_commit=False,
    )
    Base.metadata.create_all(bind=engine)

    def override_get_db() -> Iterator:
        session = TestingSessionLocal()
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    app = create_app(init_db=False)
    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_razorpay_gateway] = lambda: FakeRazorpayGateway()
    try:
        with TestClient(app) as client:
            yield client
    finally:
        app.dependency_overrides.clear()
        Base.metadata.drop_all(bind=engine)


def load_heldout(path: Path = HELDOUT_PATH) -> HeldOutFile:
    return HeldOutFile.model_validate(json.loads(path.read_text()))


def run_case(case: HeldOutCase) -> tuple[IncidentRelation, Decision]:
    with eval_client() as client:
        world = client.post("/v1/ingest/world", json=expand_world(case))
        if world.status_code != 200:
            raise RuntimeError(f"{case.case_id} world ingest failed: {world.text}")
        ingested = client.post("/v1/ingest/attempts", json=expand_attempt(case))
        if ingested.status_code != 200:
            raise RuntimeError(f"{case.case_id} attempt ingest failed: {ingested.text}")
        compiled = client.post(
            "/v1/claims/compile",
            json={"support_message_id": ingested.json()["support_message_id"]},
        )
        if compiled.status_code != 200:
            raise RuntimeError(f"{case.case_id} compile failed: {compiled.text}")
        evaluated = client.post(f"/v1/evaluate/claims/{compiled.json()['claim']['claim_id']}")
        if evaluated.status_code != 200:
            raise RuntimeError(f"{case.case_id} evaluate failed: {evaluated.text}")
        body = evaluated.json()
        return IncidentRelation(body["link"]["relation"]), Decision(body["decision"]["decision"])


def run_heldout(path: Path = HELDOUT_PATH) -> MetricReport:
    catalog = load_heldout(path)
    outcomes = []
    for case in catalog.cases:
        relation, decision = run_case(case)
        outcomes.append(score_case(case, relation, decision))
    return summarize(outcomes)


def format_report(report: MetricReport) -> str:
    def pct(value: float | None) -> str:
        return "n/a" if value is None else f"{value:.1%}"

    lines = [
        f"Held-out cases: {report.case_count}",
        f"PREVENT precision: {pct(report.prevent_precision)}",
        f"PREVENT recall: {pct(report.prevent_recall)}",
        f"SAME precision: {pct(report.same_precision)}",
        f"SAME recall: {pct(report.same_recall)}",
        f"Decision accuracy: {report.decision_accuracy:.1%}",
        f"Relation accuracy: {report.relation_accuracy:.1%}",
        f"False-positive cost: ₹{report.false_positive_cost_minor / 100:.2f}",
        f"Missed-loss cost: ₹{report.missed_loss_minor / 100:.2f}",
        f"REVIEW predictions: {report.review_count}",
        f"Documented miss confirmed: {report.documented_miss_confirmed} ({', '.join(report.documented_miss_ids) or 'none'})",
        "",
        "Outcomes:",
    ]
    for row in report.outcomes:
        flag = ""
        if row.unsafe_miss:
            flag = " UNSAFE_MISS"
        elif row.prevent_fp:
            flag = " FALSE_PREVENT"
        elif row.documented_miss:
            flag = " DOCUMENTED"
        lines.append(
            f"  {row.case_id}: gold={row.gold_decision.value}/{row.gold_relation.value} "
            f"pred={row.predicted_decision.value}/{row.predicted_relation.value}{flag}"
        )
    return "\n".join(lines)
