import asyncio
import json
import unittest
from datetime import UTC, datetime
from decimal import Decimal

import httpx

from payments_processing.domain.entities.payment import Payment, PaymentStatus
from payments_processing.domain.errors import WebhookDeliveryError
from payments_processing.infrastructure.services.webhooks.http_webhook_sender import HttpWebhookSender
from tests.mocks import payment_request

URL = "http://hooks.example/ok"


class HttpWebhookSenderTest(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.payment = Payment.build(payment_request(amount=Decimal("100.5"), webhook_url=URL), "key-1")
        self.payment.complete(PaymentStatus.SUCCEEDED, datetime(2026, 10, 7, 12, 0, tzinfo=UTC))

    def sender(self, handler, timeout_s: float = 1.0) -> HttpWebhookSender:
        client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
        self.addAsyncCleanup(client.aclose)
        return HttpWebhookSender(client, timeout_s=timeout_s)

    async def test_posts_the_payment_result_as_json_to_its_webhook_url(self):
        requests = []

        def handler(request):
            requests.append(request)
            return httpx.Response(200)

        await self.sender(handler).send(self.payment)

        [request] = requests
        self.assertEqual(request.method, "POST")
        self.assertEqual(str(request.url), URL)
        self.assertEqual(
            json.loads(request.content),
            {
                "payment_id": str(self.payment.id),
                "status": "succeeded",
                "amount": "100.50",
                "currency": "RUB",
                "processed_at": "2026-10-07T12:00:00Z",
            },
        )

    async def test_any_2xx_is_delivered(self):
        await self.sender(lambda request: httpx.Response(204)).send(self.payment)

    async def test_non_2xx_raises(self):
        for status in (302, 404, 500):
            with self.subTest(status=status):
                sender = self.sender(lambda request, status=status: httpx.Response(status))
                with self.assertRaisesRegex(WebhookDeliveryError, str(status)):
                    await sender.send(self.payment)

    async def test_transport_error_raises(self):
        for error in (httpx.ConnectError("refused"), httpx.ReadTimeout("slow")):
            with self.subTest(error=type(error).__name__):

                def handler(request, error=error):
                    raise error

                with self.assertRaises(WebhookDeliveryError):
                    await self.sender(handler).send(self.payment)

    async def test_timeout_bounds_the_whole_request(self):
        """httpx timeouts are per phase: a peer trickling bytes would never trip them."""

        async def handler(request):
            await asyncio.sleep(1)
            return httpx.Response(200)

        with self.assertRaisesRegex(WebhookDeliveryError, "timed out"):
            async with asyncio.timeout(0.5):
                await self.sender(handler, timeout_s=0.05).send(self.payment)

    async def test_response_body_is_not_read(self):
        def handler(request):
            return httpx.Response(200, stream=ExplodingStream())

        await self.sender(handler).send(self.payment)


class ExplodingStream(httpx.AsyncByteStream):
    async def __aiter__(self):
        raise AssertionError("response body was read")
        yield b""
