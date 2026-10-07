import json
import unittest
import uuid
from unittest.mock import AsyncMock, Mock, create_autospec

from faststream.rabbit import RabbitBroker, RabbitMessage

from payments_processing.application.payments.payment_processing import PaymentProcessing
from payments_processing.domain.errors import PaymentNotFoundError, WebhookDeliveryError, WebhookTargetForbiddenError
from payments_processing.presentation.consumer.handler import PaymentCreatedHandler

PAYMENT_ID = uuid.uuid4()


def message(body: bytes | None = None, headers: dict | None = None) -> Mock:
    msg = Mock(spec=RabbitMessage)
    msg.body = json.dumps({"payment_id": str(PAYMENT_ID)}).encode() if body is None else body
    msg.headers = headers or {}
    msg.message_id = "m1"
    msg.content_type = "application/json"
    msg.ack = AsyncMock()
    msg.reject = AsyncMock()
    return msg


class PaymentCreatedHandlerTest(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.processing = create_autospec(PaymentProcessing, instance=True)
        self.broker = create_autospec(RabbitBroker, instance=True)
        self.handler = PaymentCreatedHandler(self.processing, self.broker)

    async def test_success_is_acked(self):
        msg = message()

        await self.handler.handle(msg)

        self.processing.process.assert_awaited_once_with(PAYMENT_ID)
        msg.ack.assert_awaited_once()
        msg.reject.assert_not_awaited()
        self.broker.publish.assert_not_awaited()

    async def test_failed_attempts_go_to_the_next_retry_queue_then_ack(self):
        self.processing.process.side_effect = WebhookDeliveryError("HTTP 500")
        for headers, queue, next_attempt in (
            ({}, "payments.new.retry.1", 2),
            ({"x-attempt": 2}, "payments.new.retry.2", 3),
        ):
            with self.subTest(headers=headers):
                self.broker.publish.reset_mock()
                msg = message(headers=headers | {"trace": "t1"})

                with self.assertLogs("payments_processing.presentation.consumer.handler", "WARNING"):
                    await self.handler.handle(msg)

                kwargs = self.broker.publish.await_args.kwargs
                self.assertEqual(self.broker.publish.await_args.args, (msg.body,))
                self.assertEqual(kwargs["queue"].name, queue)
                self.assertEqual(kwargs["headers"], {"trace": "t1", "x-attempt": next_attempt})
                self.assertTrue(kwargs["persist"])
                self.assertEqual(kwargs["message_id"], "m1")
                msg.ack.assert_awaited_once()
                msg.reject.assert_not_awaited()

    async def test_third_failed_attempt_is_rejected_into_the_dlq(self):
        self.processing.process.side_effect = WebhookDeliveryError("HTTP 500")
        msg = message(headers={"x-attempt": 3})

        with self.assertLogs("payments_processing.presentation.consumer.handler", "ERROR"):
            await self.handler.handle(msg)

        msg.reject.assert_awaited_once_with()
        msg.ack.assert_not_awaited()
        self.broker.publish.assert_not_awaited()

    async def test_malformed_body_is_dead_lettered_without_processing(self):
        for body in (b"not-json", b"\xff", b"[]", b"{}", b'{"payment_id": 5}', b'{"payment_id": "nope"}'):
            with self.subTest(body=body):
                msg = message(body=body)

                with self.assertLogs("payments_processing.presentation.consumer.handler", "WARNING"):
                    await self.handler.handle(msg)

                msg.reject.assert_awaited_once_with()
                msg.ack.assert_not_awaited()
        self.processing.process.assert_not_awaited()
        self.broker.publish.assert_not_awaited()

    async def test_malformed_attempt_header_is_dead_lettered_without_processing(self):
        for attempt in ("abc", 0, -1, None):
            with self.subTest(attempt=attempt):
                msg = message(headers={"x-attempt": attempt})

                with self.assertLogs("payments_processing.presentation.consumer.handler", "WARNING"):
                    await self.handler.handle(msg)

                msg.reject.assert_awaited_once_with()
                msg.ack.assert_not_awaited()
        self.processing.process.assert_not_awaited()
        self.broker.publish.assert_not_awaited()

    async def test_retry_publish_failure_dead_letters_the_message(self):
        """Manual ack: an exception escaping the handler would leave the delivery unacked until consumer_timeout."""
        self.processing.process.side_effect = WebhookDeliveryError("HTTP 500")
        self.broker.publish.side_effect = ConnectionError("broker nack")
        msg = message()

        with self.assertLogs("payments_processing.presentation.consumer.handler", "ERROR"):
            await self.handler.handle(msg)

        msg.reject.assert_awaited_once_with()
        msg.ack.assert_not_awaited()

    async def test_permanent_failures_are_dead_lettered_without_retries(self):
        """Retrying cannot make a missing payment appear or a forbidden webhook target allowed."""
        for error in (PaymentNotFoundError("payment not found"), WebhookTargetForbiddenError("10.0.0.5")):
            with self.subTest(error=type(error).__name__):
                self.processing.process.side_effect = error
                msg = message()

                with self.assertLogs("payments_processing.presentation.consumer.handler", "ERROR"):
                    await self.handler.handle(msg)

                msg.reject.assert_awaited_once_with()
                msg.ack.assert_not_awaited()
        self.broker.publish.assert_not_awaited()

    async def test_retry_copy_publish_is_bounded_by_a_timeout(self):
        """A connection blocked by a RabbitMQ alarm would otherwise hang the handler and its prefetch slot."""
        self.processing.process.side_effect = WebhookDeliveryError("HTTP 500")
        handler = PaymentCreatedHandler(self.processing, self.broker, publish_timeout_s=2.5)

        with self.assertLogs("payments_processing.presentation.consumer.handler", "WARNING"):
            await handler.handle(message())

        self.assertEqual(self.broker.publish.await_args.kwargs["timeout"], 2.5)
