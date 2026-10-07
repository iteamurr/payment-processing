import unittest

from payments_processing.infrastructure.broker.client import build_broker
from payments_processing.infrastructure.broker.topology import (
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
