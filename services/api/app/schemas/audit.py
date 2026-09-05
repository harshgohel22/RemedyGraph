from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.domain.enums import AuditEventType


class AuditEventOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    merchant_id: str
    event_type: AuditEventType
    support_message_id: str | None
    remedy_request_id: str | None
    payload: dict
    created_at: datetime


class AuditListResponse(BaseModel):
    merchant_id: str
    events: list[AuditEventOut]
