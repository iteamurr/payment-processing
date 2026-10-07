from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any, Self

from sqlalchemy import CHAR, DateTime, Index, Numeric, String, Text, Uuid, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from payments_processing.domain.entities.outbox_event import OutboxEvent
from payments_processing.domain.entities.payment import Payment, PaymentStatus
from payments_processing.domain.values.money import Currency, Money


class Base(DeclarativeBase):
    """Mirrors the migrations closely enough for `alembic check`; CHECK constraints live in the migrations only."""


class PaymentRow(Base):
    """`meta` maps the `metadata` column: that attribute name is reserved on declarative classes."""

    __tablename__ = "payments"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True)
    amount: Mapped[Decimal] = mapped_column(Numeric(18, 2))
    currency: Mapped[str] = mapped_column(String(3))
    description: Mapped[str] = mapped_column(Text)
    meta: Mapped[dict[str, Any]] = mapped_column("metadata", JSONB)
    status: Mapped[str] = mapped_column(String(16))
    idempotency_key: Mapped[str] = mapped_column(String(255), unique=True)
    request_hash: Mapped[str] = mapped_column(CHAR(64))
    webhook_url: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    @staticmethod
    def insert_values(payment: Payment) -> dict[str, Any]:
        """Column values for `insert(PaymentRow).values(...)`: ON CONFLICT needs a Core insert, not session.add."""
        return {
            "id": payment.id,
            "amount": payment.money.amount,
            "currency": payment.money.currency.value,
            "description": payment.description,
            "meta": payment.metadata,
            "status": payment.status.value,
            "idempotency_key": payment.idempotency_key,
            "request_hash": payment.request_hash,
            "webhook_url": payment.webhook_url,
            "created_at": payment.created_at,
            "processed_at": payment.processed_at,
        }

    def to_payment(self) -> Payment:
        return Payment(
            id=self.id,
            money=Money(self.amount, Currency(self.currency)),
            description=self.description,
            metadata=self.meta,
            webhook_url=self.webhook_url,
            idempotency_key=self.idempotency_key,
            request_hash=self.request_hash,
            status=PaymentStatus(self.status),
            created_at=self.created_at,
            processed_at=self.processed_at,
        )


class OutboxRow(Base):
    __tablename__ = "outbox"
    __table_args__ = (Index("ix_outbox_unpublished", "created_at", postgresql_where=text("published_at IS NULL")),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True)
    event_type: Mapped[str] = mapped_column(String(64))
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    @classmethod
    def from_event(cls, event: OutboxEvent) -> Self:
        return cls(id=event.id, event_type=event.event_type, payload=event.payload, created_at=event.created_at)

    def to_event(self) -> OutboxEvent:
        return OutboxEvent(id=self.id, event_type=self.event_type, payload=self.payload, created_at=self.created_at)
