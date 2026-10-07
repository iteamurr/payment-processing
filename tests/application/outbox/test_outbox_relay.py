import asyncio
import unittest
import uuid
from unittest.mock import create_autospec

from payments_processing.application.outbox.outbox_relay import OutboxRelay
from payments_processing.domain.entities.outbox_event import OutboxEvent
from payments_processing.domain.services.outbox.event_publisher import EventPublisher
from tests.mocks import InMemoryOutboxRepository


def events(count: int) -> list[OutboxEvent]:
    return [OutboxEvent.payment_created(uuid.uuid4()) for _ in range(count)]


class OutboxRelayTest(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.publisher = create_autospec(EventPublisher, instance=True)

    def relay(self, outbox, **kwargs) -> OutboxRelay:
        return OutboxRelay(outbox, self.publisher, **kwargs)

    async def test_publishes_pending_events_in_order_and_marks_them(self):
        pending = events(3)
        outbox = InMemoryOutboxRepository(pending)

        published = await self.relay(outbox).publish_pending()

        self.assertEqual(published, 3)
        self.assertEqual([c.args[0] for c in self.publisher.publish.await_args_list], pending)
        self.assertEqual((outbox.pending, outbox.published), ([], pending))

    async def test_publish_error_leaves_the_whole_batch_pending(self):
        pending = events(3)
        outbox = InMemoryOutboxRepository(pending)
        self.publisher.publish.side_effect = [None, ConnectionError("broker down")]

        with self.assertRaises(ConnectionError):
            await self.relay(outbox).publish_pending()

        self.assertEqual((outbox.pending, outbox.published), (pending, []))

    async def test_batch_size_limits_one_run(self):
        outbox = InMemoryOutboxRepository(events(3))

        self.assertEqual(await self.relay(outbox, batch_size=2).publish_pending(), 2)
        self.assertEqual(len(outbox.pending), 1)

    async def test_run_survives_publish_errors(self):
        outbox = InMemoryOutboxRepository(events(1))
        self.publisher.publish.side_effect = [ConnectionError("broker down"), None]

        with self.assertLogs("payments_processing.application.outbox.outbox_relay", "ERROR"):
            task = asyncio.create_task(self.relay(outbox, poll_interval_s=0.01).run())
            self.addCleanup(task.cancel)
            async with asyncio.timeout(2):
                while outbox.pending:
                    await asyncio.sleep(0.01)

        self.assertEqual(len(outbox.published), 1)

    async def test_cancel_stops_run_while_waiting_for_the_next_poll(self):
        task = asyncio.create_task(self.relay(InMemoryOutboxRepository(), poll_interval_s=60).run())
        await asyncio.sleep(0.01)

        task.cancel()

        with self.assertRaises(asyncio.CancelledError):
            async with asyncio.timeout(1):
                await task

    async def test_cancel_mid_publish_leaves_the_batch_pending(self):
        """Shutdown cancels the relay; a half-published batch is rolled back and re-sent later."""
        outbox = InMemoryOutboxRepository(events(2))
        publishing = asyncio.Event()

        async def hang(event):
            publishing.set()
            await asyncio.sleep(60)

        self.publisher.publish.side_effect = hang
        task = asyncio.create_task(self.relay(outbox).run())
        await publishing.wait()

        task.cancel()

        with self.assertRaises(asyncio.CancelledError):
            await task
        self.assertEqual((len(outbox.pending), outbox.published), (2, []))
