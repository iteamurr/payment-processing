import json
import unittest
from datetime import UTC, datetime
from decimal import Decimal

import httpx

from payments_processing.domain.entities.payment import Payment, PaymentStatus
from payments_processing.domain.errors import WebhookDeliveryError
from payments_processing.infrastructure.services.payments.http_webhook_sender import HttpWebhookSender
from tests.mocks import payment_request

URL = "http://hooks.example/ok"


class HttpWebhookSenderTest(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.payment = Payment.build(payment_request(amount=Decimal("100.5"), webhook_url=URL), "key-1")
        self.payment.complete(PaymentStatus.SUCCEEDED, datetime(2026, 10, 7, 12, 0, tzinfo=UTC))

    def sender(self, handler) -> HttpWebhookSender:
        client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
        self.addAsyncCleanup(client.aclose)
        return HttpWebhookSender(client, timeout_s=1.0)

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
                "processed_at": "2026-10-07T12:00:00+00:00",
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
