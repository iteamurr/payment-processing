import asyncio
import unittest

from payments_processing.infrastructure.broker.client import build_broker
from payments_processing.infrastructure.broker.topology import (
    PAYMENTS_EXCHANGE,
    PAYMENTS_NEW,
    PAYMENTS_NEW_DLQ,
    RETRY_QUEUES,
    declare_topology,
)
from tests.live_services import RABBITMQ_URL, requires_rabbitmq


class TopologyTest(unittest.TestCase):
    def test_retry_queues_dead_letter_back_into_payments_new(self):
        for queue in RETRY_QUEUES:
            with self.subTest(queue=queue.name):
                self.assertEqual(queue.arguments["x-dead-letter-exchange"], "payments")
                self.assertEqual(queue.arguments["x-dead-letter-routing-key"], "payments.new")

    def test_queues_are_quorum_queues(self):
        for queue in (PAYMENTS_NEW, PAYMENTS_NEW_DLQ, *RETRY_QUEUES):
            with self.subTest(queue=queue.name):
                self.assertEqual(queue.arguments["x-queue-type"], "quorum")

    def test_a_message_that_keeps_crashing_the_consumer_is_dead_lettered(self):
        """Redeliveries after a consumer crash keep x-attempt unchanged; the delivery limit stops the loop."""
        self.assertEqual(PAYMENTS_NEW.arguments["x-delivery-limit"], 5)

    def test_dead_lettering_is_at_least_once(self):
        """Quorum queues dead-letter at most once by default, which could drop a message on the way to the DLQ."""
        for queue in (PAYMENTS_NEW, *RETRY_QUEUES):
            with self.subTest(queue=queue.name):
                self.assertEqual(queue.arguments["x-dead-letter-strategy"], "at-least-once")
                self.assertEqual(queue.arguments["x-overflow"], "reject-publish")

    def test_rejected_messages_go_to_the_dlq(self):
        self.assertEqual(PAYMENTS_NEW.arguments["x-dead-letter-exchange"], "payments.dlx")
        self.assertEqual(PAYMENTS_NEW.arguments["x-dead-letter-routing-key"], PAYMENTS_NEW_DLQ.routing_key)


@requires_rabbitmq
class DeclareTopologyTest(unittest.IsolatedAsyncioTestCase):
    async def test_declaring_twice_is_idempotent(self):
        broker = build_broker(RABBITMQ_URL, prefetch_count=1)
        await broker.connect()
        self.addAsyncCleanup(broker.stop)

        await declare_topology(broker)
        await declare_topology(broker)

    async def test_a_message_redelivered_past_the_limit_lands_in_the_dlq(self):
        """What a consumer that crashes on a message produces: unacked redeliveries until the limit is exceeded.

        At-least-once dead-lettering is asynchronous, so the DLQ is polled. Run with the compose consumer stopped."""
        broker = build_broker(RABBITMQ_URL, prefetch_count=1)
        await broker.connect()
        self.addAsyncCleanup(broker.stop)
        await declare_topology(broker)
        new = await broker.declare_queue(PAYMENTS_NEW)
        dlq = await broker.declare_queue(PAYMENTS_NEW_DLQ)
        await new.purge()
        await dlq.purge()
        await broker.publish(b"poison", exchange=PAYMENTS_EXCHANGE, routing_key=PAYMENTS_NEW.routing_key)

        for _ in range(10):
            message = await new.get(fail=False)
            if message is None:
                break
            await message.nack(requeue=True)
            await asyncio.sleep(0.05)

        async with asyncio.timeout(5):
            while (dead := await dlq.get(no_ack=True, fail=False)) is None:
                await asyncio.sleep(0.05)
        self.assertEqual(dead.body, b"poison")
