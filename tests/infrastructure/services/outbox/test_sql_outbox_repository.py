import uuid
from datetime import UTC, datetime, timedelta

from payments_processing.domain.entities.outbox_event import PAYMENT_CREATED, OutboxEvent
from payments_processing.infrastructure.db.models import OutboxRow
from payments_processing.infrastructure.services.outbox.sql_outbox_repository import SqlOutboxRepository
from tests.live_services import DatabaseTestCase


class SqlOutboxRepositoryTest(DatabaseTestCase):
    async def asyncSetUp(self):
        await super().asyncSetUp()
        self.outbox = SqlOutboxRepository(self.sessions)

    async def insert_events(self, count: int) -> list[OutboxEvent]:
        """Inserted newest first, so the oldest-first order in assertions comes from created_at."""
        start = datetime.now(UTC)
        events = [
            OutboxEvent(uuid.uuid4(), PAYMENT_CREATED, {"payment_id": str(uuid.uuid4())}, start + timedelta(seconds=i))
            for i in range(count)
        ]
        async with self.sessions.begin() as session:
            session.add_all(OutboxRow.from_event(event) for event in reversed(events))
        return events

    async def pending(self, limit: int = 100) -> list[OutboxEvent]:
        """Unpublished events as the next relay run would see them; marks nothing."""
        async with self.outbox.lock_pending(limit) as batch:
            return batch.events

    async def test_yields_unpublished_oldest_first_and_publishes_the_marked_ones(self):
        events = await self.insert_events(3)

        async with self.outbox.lock_pending(100) as batch:
            self.assertEqual(batch.events, events)
            for event in batch.events:
                batch.mark_published(event)

        self.assertEqual(await self.pending(), [])

    async def test_only_marked_events_are_published(self):
        events = await self.insert_events(3)

        async with self.outbox.lock_pending(100) as batch:
            batch.mark_published(events[0])

        self.assertEqual(await self.pending(), events[1:])

    async def test_exception_in_the_block_publishes_nothing(self):
        events = await self.insert_events(2)

        with self.assertRaises(ConnectionError):
            async with self.outbox.lock_pending(100) as batch:
                batch.mark_published(events[0])
                raise ConnectionError("broker down")

        self.assertEqual(await self.pending(), events)

    async def test_limit(self):
        events = await self.insert_events(3)

        self.assertEqual(await self.pending(limit=2), events[:2])

    async def test_locked_events_are_skipped_by_a_concurrent_relay(self):
        events = await self.insert_events(3)

        async with self.outbox.lock_pending(2) as first:
            async with self.outbox.lock_pending(100) as second:
                self.assertEqual(first.events, events[:2])
                self.assertEqual(second.events, events[2:])
