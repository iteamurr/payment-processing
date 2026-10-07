import uuid
from datetime import UTC, datetime, timedelta

from payments_processing.domain.entities.outbox_event import PAYMENT_CREATED, OutboxEvent
from payments_processing.infrastructure.db.models import OutboxRow
from payments_processing.infrastructure.services.outbox.sql_outbox_repository import SqlOutboxRepository
from tests.infrastructure.db import DatabaseTestCase


class SqlOutboxRepositoryTest(DatabaseTestCase):
    async def asyncSetUp(self):
        await super().asyncSetUp()
        self.outbox = SqlOutboxRepository(self.sessions)

    async def insert_events(self, count: int) -> list[OutboxEvent]:
        start = datetime.now(UTC)
        events = [
            OutboxEvent(uuid.uuid4(), PAYMENT_CREATED, {"payment_id": str(uuid.uuid4())}, start + timedelta(seconds=i))
            for i in range(count)
        ]
        async with self.sessions.begin() as session:
            # inserted newest first to prove ordering comes from created_at
            for event in reversed(events):
                session.add(OutboxRow(**{f: getattr(event, f) for f in ("id", "event_type", "payload", "created_at")}))
        return events

    async def test_yields_unpublished_oldest_first_and_marks_them_published(self):
        events = await self.insert_events(3)

        async with self.outbox.lock_pending(100) as locked:
            self.assertEqual(locked, events)

        async with self.outbox.lock_pending(100) as locked:
            self.assertEqual(locked, [])

    async def test_exception_in_the_block_leaves_events_unpublished(self):
        events = await self.insert_events(2)

        with self.assertRaises(ConnectionError):
            async with self.outbox.lock_pending(100):
                raise ConnectionError("broker down")

        async with self.outbox.lock_pending(100) as locked:
            self.assertEqual(locked, events)

    async def test_limit(self):
        events = await self.insert_events(3)

        async with self.outbox.lock_pending(2) as locked:
            self.assertEqual(locked, events[:2])

    async def test_locked_events_are_skipped_by_a_concurrent_relay(self):
        events = await self.insert_events(3)

        async with self.outbox.lock_pending(2) as first:
            async with self.outbox.lock_pending(100) as second:
                self.assertEqual(first, events[:2])
                self.assertEqual(second, events[2:])
