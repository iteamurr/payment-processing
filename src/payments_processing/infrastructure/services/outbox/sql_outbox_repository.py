from __future__ import annotations

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from payments_processing.domain.services.outbox.outbox_repository import OutboxBatch, OutboxRepository
from payments_processing.infrastructure.db.models import OutboxRow


@dataclass
class SqlOutboxRepository(OutboxRepository):
    sessions: async_sessionmaker[AsyncSession]

    @asynccontextmanager
    async def lock_pending(self, limit: int) -> AsyncGenerator[OutboxBatch]:
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
            batch = OutboxBatch([row.to_event() for row in rows])
            yield batch
            published_at = datetime.now(UTC)
            published = {event.id for event in batch.published}
            for row in rows:
                if row.id in published:
                    row.published_at = published_at
