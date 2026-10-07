import json
import unittest
import uuid
from unittest.mock import create_autospec

from faststream.rabbit import RabbitBroker
from pamqp.commands import Basic

from payments_processing.domain.entities.outbox_event import OutboxEvent
from payments_processing.infrastructure.broker.client import build_broker
from payments_processing.infrastructure.broker.topology import PAYMENTS_EXCHANGE, PAYMENTS_NEW, declare_topology
from payments_processing.infrastructure.services.outbox.rabbit_event_publisher import (
    PublishNotConfirmedError,
    RabbitEventPublisher,
)
from tests.live_services import RABBITMQ_URL, requires_rabbitmq


class RabbitEventPublisherTest(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.broker = create_autospec(RabbitBroker, instance=True)
        self.event = OutboxEvent.payment_created(uuid.uuid4())

    async def test_publishes_persistent_message_to_payments_new(self):
        self.broker.publish.return_value = Basic.Ack()

        await RabbitEventPublisher(self.broker).publish(self.event)

        self.broker.publish.assert_awaited_once_with(
            self.event.payload,
            exchange=PAYMENTS_EXCHANGE,
            routing_key="payments.new",
            persist=True,
            message_id=str(self.event.id),
            message_type="payment.created",
            timeout=10.0,
        )

    async def test_publish_is_bounded_by_the_timeout(self):
        """A connection blocked by a RabbitMQ alarm would otherwise hold the relay's row locks indefinitely."""
        self.broker.publish.return_value = Basic.Ack()

        await RabbitEventPublisher(self.broker, timeout_s=2.5).publish(self.event)

        self.assertEqual(self.broker.publish.await_args.kwargs["timeout"], 2.5)

    async def test_nack_raises(self):
        self.broker.publish.return_value = Basic.Nack()

        with self.assertRaises(PublishNotConfirmedError):
            await RabbitEventPublisher(self.broker).publish(self.event)


@requires_rabbitmq
class RabbitEventPublisherIntegrationTest(unittest.IsolatedAsyncioTestCase):
    async def test_event_lands_in_payments_new(self):
        broker = build_broker(RABBITMQ_URL, prefetch_count=1)
        await broker.connect()
        self.addAsyncCleanup(broker.stop)
        await declare_topology(broker)
        queue = await broker.declare_queue(PAYMENTS_NEW)
        await queue.purge()
        event = OutboxEvent.payment_created(uuid.uuid4())

        await RabbitEventPublisher(broker).publish(event)

        message = await queue.get(no_ack=True, timeout=5)
        self.assertEqual(json.loads(message.body), event.payload)
        self.assertEqual(message.message_id, str(event.id))
