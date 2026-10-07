import unittest
from unittest.mock import create_autospec

from faststream.rabbit import RabbitBroker, TestRabbitBroker

from payments_processing.infrastructure.broker.rabbit import PAYMENTS_EXCHANGE, PAYMENTS_NEW
from payments_processing.presentation.consumer.app import subscribe
from payments_processing.presentation.consumer.handler import PaymentCreatedHandler


class SubscribeTest(unittest.IsolatedAsyncioTestCase):
    async def test_messages_from_payments_new_reach_the_handler(self):
        broker = RabbitBroker()
        handler = create_autospec(PaymentCreatedHandler, instance=True)
        subscribe(broker, handler)

        async with TestRabbitBroker(broker) as test_broker:
            await test_broker.publish(b"raw-body", exchange=PAYMENTS_EXCHANGE, routing_key=PAYMENTS_NEW.routing_key)

        handler.handle.assert_awaited_once()
        self.assertEqual(handler.handle.await_args.args[0].body, b"raw-body")
