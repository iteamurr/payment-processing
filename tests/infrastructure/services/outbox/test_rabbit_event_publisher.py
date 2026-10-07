import json
import unittest
import uuid
from unittest.mock import create_autospec

from faststream.rabbit import RabbitBroker
from pamqp.commands import Basic

from payments_processing.domain.entities.outbox_event import OutboxEvent
from payments_processing.infrastructure.broker.rabbit import (
    PAYMENTS_EXCHANGE,
    PAYMENTS_NEW,
    build_broker,
    declare_topology,
)
from payments_processing.infrastructure.services.outbox.rabbit_event_publisher import (
    PublishNotConfirmedError,
    RabbitEventPublisher,
)
from tests.infrastructure.broker.test_rabbit import RABBITMQ_URL, requires_rabbitmq


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
        )

    async def test_nack_raises(self):
        self.broker.publish.return_value = Basic.Nack()

        with self.assertRaises(PublishNotConfirmedError):
            await RabbitEventPublisher(self.broker).publish(self.event)


@requires_rabbitmq
class RabbitEventPublisherIntegrationTest(unittest.IsolatedAsyncioTestCase):
    async def test_event_lands_in_payments_new(self):
        broker = build_broker(RABBITMQ_URL)
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
