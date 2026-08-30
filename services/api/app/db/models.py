from datetime import datetime

from sqlalchemy import CheckConstraint, ForeignKeyConstraint, JSON, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


def _utcnow() -> datetime:
    return datetime.now().astimezone()


class Merchant(Base):
    __tablename__ = "merchants"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)

    customers: Mapped[list["Customer"]] = relationship(back_populates="merchant", cascade="all, delete-orphan")
    orders: Mapped[list["Order"]] = relationship(back_populates="merchant", cascade="all, delete-orphan")
    support_messages: Mapped[list["SupportMessage"]] = relationship(
        back_populates="merchant", cascade="all, delete-orphan"
    )
    remedy_requests: Mapped[list["RemedyRequest"]] = relationship(
        back_populates="merchant", cascade="all, delete-orphan"
    )
    audit_events: Mapped[list["AuditEvent"]] = relationship(
        back_populates="merchant", cascade="all, delete-orphan"
    )
    entitlements: Mapped[list["Entitlement"]] = relationship(
        back_populates="merchant", cascade="all, delete-orphan"
    )
    remedy_reservations: Mapped[list["RemedyReservation"]] = relationship(
        back_populates="merchant", cascade="all, delete-orphan"
    )


class Customer(Base):
    __tablename__ = "customers"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    merchant_id: Mapped[str] = mapped_column(ForeignKey("merchants.id", ondelete="CASCADE"), nullable=False)
    display_name: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)

    merchant: Mapped[Merchant] = relationship(back_populates="customers")


class Order(Base):
    __tablename__ = "orders"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    merchant_id: Mapped[str] = mapped_column(ForeignKey("merchants.id", ondelete="CASCADE"), nullable=False)
    customer_id: Mapped[str] = mapped_column(ForeignKey("customers.id", ondelete="RESTRICT"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    merchant: Mapped[Merchant] = relationship(back_populates="orders")
    lines: Mapped[list["OrderLine"]] = relationship(back_populates="order", cascade="all, delete-orphan")


class OrderLine(Base):
    __tablename__ = "order_lines"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    order_id: Mapped[str] = mapped_column(ForeignKey("orders.id", ondelete="CASCADE"), nullable=False)
    product_id: Mapped[str] = mapped_column(String(128), nullable=False)
    product_name: Mapped[str] = mapped_column(String(255), nullable=False)
    quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    unit_price_minor: Mapped[int] = mapped_column(Integer, nullable=False)

    order: Mapped[Order] = relationship(back_populates="lines")
    units: Mapped[list["ItemUnit"]] = relationship(back_populates="order_line", cascade="all, delete-orphan")


class ItemUnit(Base):
    __tablename__ = "item_units"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    order_line_id: Mapped[str] = mapped_column(ForeignKey("order_lines.id", ondelete="CASCADE"), nullable=False)
    product_id: Mapped[str] = mapped_column(String(128), nullable=False)
    parent_unit_id: Mapped[str | None] = mapped_column(ForeignKey("item_units.id", ondelete="SET NULL"))

    order_line: Mapped[OrderLine] = relationship(back_populates="units")


class SupportMessage(Base):
    __tablename__ = "support_messages"
    __table_args__ = (
        UniqueConstraint("merchant_id", "external_message_id", name="uq_support_messages_external"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    merchant_id: Mapped[str] = mapped_column(ForeignKey("merchants.id", ondelete="CASCADE"), nullable=False)
    customer_id: Mapped[str] = mapped_column(ForeignKey("customers.id", ondelete="RESTRICT"), nullable=False)
    channel: Mapped[str] = mapped_column(String(32), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    order_reference: Mapped[str | None] = mapped_column(String(128))
    external_message_id: Mapped[str | None] = mapped_column(String(128))
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)

    merchant: Mapped[Merchant] = relationship(back_populates="support_messages")
    remedy_requests: Mapped[list["RemedyRequest"]] = relationship(back_populates="support_message")


class RemedyRequest(Base):
    __tablename__ = "remedy_requests"
    __table_args__ = (
        UniqueConstraint("merchant_id", "idempotency_key", name="uq_remedy_requests_idempotency"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    merchant_id: Mapped[str] = mapped_column(ForeignKey("merchants.id", ondelete="CASCADE"), nullable=False)
    customer_id: Mapped[str] = mapped_column(ForeignKey("customers.id", ondelete="RESTRICT"), nullable=False)
    support_message_id: Mapped[str] = mapped_column(
        ForeignKey("support_messages.id", ondelete="RESTRICT"), nullable=False
    )
    incident_id: Mapped[str | None] = mapped_column(String(64))
    item_unit_id: Mapped[str | None] = mapped_column(ForeignKey("item_units.id", ondelete="SET NULL"))
    remedy_type: Mapped[str] = mapped_column(String(32), nullable=False)
    amount_minor: Mapped[int] = mapped_column(Integer, nullable=False)
    entitlement_consumption_minor: Mapped[int] = mapped_column(Integer, nullable=False)
    merchant_cost_minor: Mapped[int | None] = mapped_column(Integer)
    currency: Mapped[str] = mapped_column(String(8), nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(128), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)

    merchant: Mapped[Merchant] = relationship(back_populates="remedy_requests")
    support_message: Mapped[SupportMessage] = relationship(back_populates="remedy_requests")




class Entitlement(Base):
    """One lockable money row per incident. settled + reserved must never exceed allowed."""

    __tablename__ = "entitlements"
    __table_args__ = (
        CheckConstraint(
            "settled_minor + reserved_minor <= allowed_minor",
            name="ck_entitlement_cap",
        ),
        CheckConstraint("settled_minor >= 0", name="ck_entitlement_settled_nonneg"),
        CheckConstraint("reserved_minor >= 0", name="ck_entitlement_reserved_nonneg"),
    )

    merchant_id: Mapped[str] = mapped_column(ForeignKey("merchants.id", ondelete="CASCADE"), primary_key=True)
    incident_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    allowed_minor: Mapped[int] = mapped_column(Integer, nullable=False)
    settled_minor: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    reserved_minor: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)

    merchant: Mapped[Merchant] = relationship(back_populates="entitlements")


class RemedyReservation(Base):
    __tablename__ = "remedy_reservations"
    __table_args__ = (
        UniqueConstraint("merchant_id", "idempotency_key", name="uq_reservations_idempotency"),
        ForeignKeyConstraint(
            ["merchant_id", "incident_id"],
            ["entitlements.merchant_id", "entitlements.incident_id"],
            ondelete="CASCADE",
            name="fk_reservations_entitlement",
        ),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    merchant_id: Mapped[str] = mapped_column(ForeignKey("merchants.id", ondelete="CASCADE"), nullable=False)
    incident_id: Mapped[str] = mapped_column(String(64), nullable=False)
    remedy_request_id: Mapped[str] = mapped_column(String(64), nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(128), nullable=False)
    amount_minor: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)

    merchant: Mapped[Merchant] = relationship(back_populates="remedy_reservations")

class AuditEvent(Base):
    __tablename__ = "audit_events"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    merchant_id: Mapped[str] = mapped_column(ForeignKey("merchants.id", ondelete="CASCADE"), nullable=False)
    event_type: Mapped[str] = mapped_column(String(64), nullable=False)
    support_message_id: Mapped[str | None] = mapped_column(String(64))
    remedy_request_id: Mapped[str | None] = mapped_column(String(64))
    payload: Mapped[dict] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)

    merchant: Mapped[Merchant] = relationship(back_populates="audit_events")
