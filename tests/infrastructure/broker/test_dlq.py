import json
import unittest
import uuid

from payments_processing.infrastructure.broker.client import build_broker
from payments_processing.infrastructure.broker.dlq import replay_dead_letters
from payments_processing.infrastructure.broker.topology import PAYMENTS_NEW, PAYMENTS_NEW_DLQ, declare_topology
from tests.live_services import RABBITMQ_URL, requires_rabbitmq


@requires_rabbitmq
class ReplayDeadLettersTest(unittest.IsolatedAsyncioTestCase):
    """Run with the compose consumer stopped: it would take the replayed messages from payments.new."""

    async def asyncSetUp(self):
        self.broker = build_broker(RABBITMQ_URL, prefetch_count=1)
        await self.broker.connect()
        self.addAsyncCleanup(self.broker.stop)
        await declare_topology(self.broker)
        self.new = await self.broker.declare_queue(PAYMENTS_NEW)
        self.dlq = await self.broker.declare_queue(PAYMENTS_NEW_DLQ)
        await self.new.purge()
        await self.dlq.purge()

    async def dead_letter(self, body: dict[str, str]) -> None:
        await self.broker.publish(
            json.dumps(body).encode(),
            queue=PAYMENTS_NEW_DLQ.name,
            headers={"x-attempt": 3, "x-first-death-reason": "expired", "trace": "t1"},
            message_id="m1",
            content_type="application/json",
        )

    async def test_moves_dead_letters_back_to_payments_new_as_first_attempts(self):
        bodies = [{"payment_id": str(uuid.uuid4())} for _ in range(2)]
        for body in bodies:
            await self.dead_letter(body)

        replayed = await replay_dead_letters(self.broker)

        self.assertEqual(replayed, 2)
        self.assertIsNone(await self.dlq.get(no_ack=True, fail=False))
        for body in bodies:
            message = await self.new.get(no_ack=True, timeout=5)
            assert message is not None
            self.assertEqual(json.loads(message.body), body)
            self.assertEqual(message.headers, {"trace": "t1"})
            self.assertEqual(message.message_id, "m1")

    async def test_empty_dlq_replays_nothing(self):
        self.assertEqual(await replay_dead_letters(self.broker), 0)
