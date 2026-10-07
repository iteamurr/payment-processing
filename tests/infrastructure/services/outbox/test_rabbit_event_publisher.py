import json
import unittest
import uuid
from unittest.mock import AsyncMock, create_autospec, patch

from aiormq.exceptions import AMQPConnectionError
from faststream.rabbit import RabbitBroker

from payments_processing.domain.entities.outbox_event import OutboxEvent
from payments_processing.infrastructure.broker.client import build_broker
from payments_processing.infrastructure.broker.topology import PAYMENTS_EXCHANGE, PAYMENTS_NEW, declare_topology
from payments_processing.infrastructure.services.outbox.rabbit_event_publisher import RabbitEventPublisher
from tests.live_services import RABBITMQ_URL, requires_rabbitmq

TOPOLOGY = "payments_processing.infrastructure.services.outbox.rabbit_event_publisher.declare_topology"


class RabbitEventPublisherTest(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.broker = create_autospec(RabbitBroker, instance=True)
        self.event = OutboxEvent.payment_created(uuid.uuid4())
        patcher = patch(TOPOLOGY, new_callable=AsyncMock)
        self.declare_topology = patcher.start()
        self.addCleanup(patcher.stop)

    async def test_publishes_persistent_message_to_payments_new(self):
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
        await RabbitEventPublisher(self.broker, timeout_s=2.5).publish(self.event)

        self.assertEqual(self.broker.publish.await_args.kwargs["timeout"], 2.5)

    async def test_connects_and_declares_the_topology_once_before_the_first_publish(self):
        """The api starts without the broker; the relay's first successful publish brings the connection up."""
        publisher = RabbitEventPublisher(self.broker)

        await publisher.publish(self.event)
        await publisher.publish(self.event)

        self.broker.connect.assert_awaited_once_with()
        self.declare_topology.assert_awaited_once_with(self.broker)
        self.assertEqual(self.broker.publish.await_count, 2)

    async def test_failed_connect_is_retried_on_the_next_publish(self):
        self.broker.connect.side_effect = [AMQPConnectionError("refused"), None]
        publisher = RabbitEventPublisher(self.broker)

        with self.assertRaises(AMQPConnectionError):
            await publisher.publish(self.event)
        self.broker.publish.assert_not_awaited()

        await publisher.publish(self.event)

        self.assertEqual(self.broker.connect.await_count, 2)
        self.broker.publish.assert_awaited_once()


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
