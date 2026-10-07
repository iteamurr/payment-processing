import json
import unittest

import httpx

from payments_processing.domain.errors import WebhookDeliveryError
from payments_processing.infrastructure.services.payments.http_webhook_sender import HttpWebhookSender

URL = "http://hooks.example/ok"
PAYLOAD = {"payment_id": "p1", "status": "succeeded"}


class HttpWebhookSenderTest(unittest.IsolatedAsyncioTestCase):
    def sender(self, handler) -> HttpWebhookSender:
        client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
        self.addAsyncCleanup(client.aclose)
        return HttpWebhookSender(client, timeout_s=1.0)

    async def test_posts_payload_as_json(self):
        requests = []

        def handler(request):
            requests.append(request)
            return httpx.Response(200)

        await self.sender(handler).send(URL, PAYLOAD)

        self.assertEqual(requests[0].method, "POST")
        self.assertEqual(str(requests[0].url), URL)
        self.assertEqual(json.loads(requests[0].content), PAYLOAD)

    async def test_any_2xx_is_delivered(self):
        await self.sender(lambda request: httpx.Response(204)).send(URL, PAYLOAD)

    async def test_non_2xx_raises(self):
        for status in (302, 404, 500):
            with self.subTest(status=status):
                sender = self.sender(lambda request, status=status: httpx.Response(status))
                with self.assertRaisesRegex(WebhookDeliveryError, str(status)):
                    await sender.send(URL, PAYLOAD)

    async def test_transport_error_raises(self):
        for error in (httpx.ConnectError("refused"), httpx.ReadTimeout("slow")):
            with self.subTest(error=type(error).__name__):

                def handler(request, error=error):
                    raise error

                with self.assertRaises(WebhookDeliveryError):
                    await self.sender(handler).send(URL, PAYLOAD)
