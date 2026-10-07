from __future__ import annotations

import uuid
from dataclasses import dataclass

from sqlalchemy import select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from payments_processing.domain.entities.outbox_event import OutboxEvent
from payments_processing.domain.entities.payment import Payment, PaymentStatus
from payments_processing.domain.services.payments.payment_repository import PaymentRepository
from payments_processing.infrastructure.db.models import OutboxRow, PaymentRow


@dataclass
class SqlPaymentRepository(PaymentRepository):
    sessions: async_sessionmaker[AsyncSession]

    async def add(self, payment: Payment, event: OutboxEvent) -> Payment:
        """On a taken key ON CONFLICT waits for the competing transaction, so its row is visible to the SELECT."""
        async with self.sessions.begin() as session:
            inserted = await session.scalar(
                insert(PaymentRow)
                .values(PaymentRow.insert_values(payment))
                .on_conflict_do_nothing(index_elements=["idempotency_key"])
                .returning(PaymentRow.id)
            )
            if inserted is None:
                existing = await session.execute(
                    select(PaymentRow).where(PaymentRow.idempotency_key == payment.idempotency_key)
                )
                return existing.scalar_one().to_payment()
            session.add(OutboxRow.from_event(event))
        return payment

    async def get(self, payment_id: uuid.UUID) -> Payment | None:
        async with self.sessions() as session:
            row = await session.get(PaymentRow, payment_id)
        return row.to_payment() if row else None

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
