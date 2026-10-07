from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Any

from sqlalchemy import select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from payments_processing.domain.entities.outbox_event import OutboxEvent
from payments_processing.domain.entities.payment import Payment, PaymentStatus
from payments_processing.domain.services.payments.payment_repository import PaymentRepository
from payments_processing.domain.values.money import Currency, Money
from payments_processing.infrastructure.db.models import OutboxRow, PaymentRow


@dataclass
class SqlPaymentRepository(PaymentRepository):
    sessions: async_sessionmaker[AsyncSession]

    async def add(self, payment: Payment, event: OutboxEvent) -> Payment:
        async with self.sessions.begin() as session:
            inserted = await session.scalar(
                insert(PaymentRow)
                .values(_to_values(payment))
                .on_conflict_do_nothing(index_elements=["idempotency_key"])
                .returning(PaymentRow.id)
            )
            if inserted is None:
                # ON CONFLICT waited for the competing transaction, so its row is committed and visible
                existing = await session.execute(
                    select(PaymentRow).where(PaymentRow.idempotency_key == payment.idempotency_key)
                )
                return _to_entity(existing.scalar_one())
            session.add(
                OutboxRow(id=event.id, event_type=event.event_type, payload=event.payload, created_at=event.created_at)
            )
        return payment

    async def get(self, payment_id: uuid.UUID) -> Payment | None:
        async with self.sessions() as session:
            row = await session.get(PaymentRow, payment_id)
        return _to_entity(row) if row else None

    async def save_result(self, payment: Payment) -> bool:
        async with self.sessions.begin() as session:
            updated = await session.scalar(
                update(PaymentRow)
                .where(PaymentRow.id == payment.id, PaymentRow.status == PaymentStatus.PENDING.value)
                .values(status=payment.status.value, processed_at=payment.processed_at)
                .returning(PaymentRow.id)
                .execution_options(synchronize_session=False)
            )
        return updated is not None


def _to_values(payment: Payment) -> dict[str, Any]:
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


def _to_entity(row: PaymentRow) -> Payment:
    return Payment(
        id=row.id,
        money=Money(row.amount, Currency(row.currency)),
        description=row.description,
        metadata=row.meta,
        webhook_url=row.webhook_url,
        idempotency_key=row.idempotency_key,
        request_hash=row.request_hash,
        status=PaymentStatus(row.status),
        created_at=row.created_at,
        processed_at=row.processed_at,
    )
