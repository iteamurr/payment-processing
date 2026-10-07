import os
import unittest

from payments_processing.infrastructure.broker.rabbit import (
    PAYMENTS_NEW,
    PAYMENTS_NEW_DLQ,
    RETRY_QUEUES,
    build_broker,
    declare_topology,
    retry_queue,
)

RABBITMQ_URL = os.environ.get("RABBITMQ_URL")
requires_rabbitmq = unittest.skipUnless(RABBITMQ_URL, "RABBITMQ_URL is not set")


class RetryQueueTest(unittest.TestCase):
    def test_failed_attempts_one_and_two_wait_two_then_four_seconds(self):
        self.assertEqual(retry_queue(1).name, "payments.new.retry.1")
        self.assertEqual(retry_queue(1).arguments["x-message-ttl"], 2000)
        self.assertEqual(retry_queue(2).name, "payments.new.retry.2")
        self.assertEqual(retry_queue(2).arguments["x-message-ttl"], 4000)

    def test_third_failed_attempt_has_no_retry(self):
        self.assertIsNone(retry_queue(3))
        self.assertIsNone(retry_queue(4))

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
        broker = build_broker(RABBITMQ_URL)
        await broker.connect()
        self.addAsyncCleanup(broker.stop)

        await declare_topology(broker)
        await declare_topology(broker)
