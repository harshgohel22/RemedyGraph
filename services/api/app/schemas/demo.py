from pydantic import BaseModel, Field

from app.domain.enums import Channel, Decision
from app.evaluation.schema import MetricReport
from app.schemas.audit import AuditEventOut
from app.schemas.claims import CompiledClaim
from app.schemas.execution import CaseExecutionResponse
from app.schemas.incidents import LinkClaimResponse
from app.schemas.ledger import EntitlementResponse
from app.schemas.retrieval import RetrievalResponse


class DemoScenarioInfo(BaseModel):
    scenario_id: str
    title: str
    expected_decision: Decision
    summary: str


class DemoRunRequest(BaseModel):
    scenario_id: str = Field(min_length=1)


class DemoRunResponse(BaseModel):
    scenario_id: str
    title: str
    expected_decision: Decision
    merchant_id: str
    customer_id: str
    support_message_id: str
    claim: CompiledClaim
    retrieval: RetrievalResponse
    link: LinkClaimResponse
    execution: CaseExecutionResponse
    ledger: EntitlementResponse | None
    audit: list[AuditEventOut]
    channel: Channel
    message_body: str
