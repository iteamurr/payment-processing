from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from payments_processing.domain.entities.outbox_event import OutboxEvent
from payments_processing.domain.services.outbox.outbox_repository import OutboxRepository
from payments_processing.infrastructure.db.models import OutboxRow


@dataclass
class SqlOutboxRepository(OutboxRepository):
    sessions: async_sessionmaker[AsyncSession]

    @asynccontextmanager
    async def lock_pending(self, limit: int) -> AsyncIterator[list[OutboxEvent]]:
        """FOR UPDATE SKIP LOCKED lets several relays (api replicas) share the table without double work."""
        async with self.sessions.begin() as session:
            rows = list(
                await session.scalars(
                    select(OutboxRow)
                    .where(OutboxRow.published_at.is_(None))
                    .order_by(OutboxRow.created_at)
                    .limit(limit)
                    .with_for_update(skip_locked=True)
                )
            )
            yield [
                OutboxEvent(id=r.id, event_type=r.event_type, payload=r.payload, created_at=r.created_at) for r in rows
            ]
            published_at = datetime.now(UTC)
            for row in rows:
                row.published_at = published_at
