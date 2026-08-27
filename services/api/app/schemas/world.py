from datetime import datetime

from pydantic import BaseModel, Field, field_validator

from app.domain.enums import Channel, Currency, RemedyStatus, RemedyType
from app.schemas.ingest import MinorUnits


class WorldItemUnitIn(BaseModel):
    unit_id: str = Field(min_length=1)
    parent_unit_id: str | None = None


class WorldOrderLineIn(BaseModel):
    order_line_id: str = Field(min_length=1)
    product_id: str = Field(min_length=1)
    product_name: str = Field(min_length=1)
    quantity: int = Field(ge=1)
    unit_price_minor: MinorUnits
    units: list[WorldItemUnitIn]


class WorldOrderIn(BaseModel):
    order_id: str = Field(min_length=1)
    customer_id: str = Field(min_length=1)
    created_at: datetime
    lines: list[WorldOrderLineIn]


class WorldCustomerIn(BaseModel):
    customer_id: str = Field(min_length=1)
    display_name: str = Field(min_length=1)


class WorldSupportMessageIn(BaseModel):
    support_message_id: str = Field(min_length=1)
    customer_id: str = Field(min_length=1)
    channel: Channel
    body: str = Field(min_length=1)
    occurred_at: datetime
    order_reference: str | None = None
    external_message_id: str | None = None

    @field_validator("order_reference", "external_message_id", mode="before")
    @classmethod
    def blank_to_none(cls, value: object) -> object:
        if value == "":
            return None
        return value


class WorldHistoricalRemedyIn(BaseModel):
    remedy_request_id: str = Field(min_length=1)
    support_message_id: str = Field(min_length=1)
    customer_id: str = Field(min_length=1)
    remedy_type: RemedyType
    amount_minor: MinorUnits
    entitlement_consumption_minor: MinorUnits
    merchant_cost_minor: MinorUnits | None = None
    currency: Currency = Currency.INR
    idempotency_key: str = Field(min_length=10, pattern=r"^[A-Za-z0-9_-]+$")
    status: RemedyStatus
    item_unit_id: str | None = None


class WorldIngestRequest(BaseModel):
    merchant_id: str = Field(min_length=1)
    merchant_name: str = Field(min_length=1)
    replace: bool = True
    customers: list[WorldCustomerIn]
    orders: list[WorldOrderIn] = []
    support_messages: list[WorldSupportMessageIn] = []
    historical_remedies: list[WorldHistoricalRemedyIn] = []


class WorldIngestResponse(BaseModel):
    merchant_id: str
    customer_count: int
    order_count: int
    unit_count: int
    support_message_count: int
    historical_remedy_count: int
    audit_id: str
    replaced: bool
