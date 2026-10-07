import asyncio
import hashlib
import hmac
import json
import time
import unittest
from datetime import UTC, datetime
from decimal import Decimal

import httpx

from payments_processing.domain.entities.payment import Payment, PaymentStatus
from payments_processing.domain.errors import WebhookDeliveryError, WebhookTargetForbiddenError
from payments_processing.infrastructure.services.webhooks.http_webhook_sender import HttpWebhookSender
from tests.mocks import payment_request

URL = "http://hooks.example/ok"
SECRET = "webhook-secret"


class HttpWebhookSenderTest(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.payment = Payment.build(payment_request(amount=Decimal("100.5"), webhook_url=URL), "key-1")
        self.payment.complete(PaymentStatus.SUCCEEDED, datetime(2026, 10, 7, 12, 0, tzinfo=UTC))

    def sender(self, handler, timeout_s: float = 1.0, allowed_hosts=frozenset({"hooks.example"})) -> HttpWebhookSender:
        client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
        self.addAsyncCleanup(client.aclose)
        return HttpWebhookSender(client, secret=SECRET, timeout_s=timeout_s, allowed_hosts=allowed_hosts)

    def payment_to(self, url: str) -> Payment:
        payment = Payment.build(payment_request(webhook_url=url), "key-2")
        payment.complete(PaymentStatus.SUCCEEDED, datetime(2026, 10, 7, 12, 0, tzinfo=UTC))
        return payment

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

    async def test_signs_timestamp_and_body_with_the_shared_secret(self):
        """The receiver recomputes the HMAC over "{timestamp}.{body}" and rejects stale timestamps."""
        requests = []

        def handler(request):
            requests.append(request)
            return httpx.Response(200)

        await self.sender(handler).send(self.payment)

        [request] = requests
        timestamp = request.headers["X-Webhook-Timestamp"]
        expected = hmac.new(SECRET.encode(), f"{timestamp}.".encode() + request.content, hashlib.sha256).hexdigest()
        self.assertEqual(request.headers["X-Webhook-Signature"], f"sha256={expected}")
        self.assertLess(abs(int(timestamp) - time.time()), 5)
        self.assertEqual(request.headers["Content-Type"], "application/json")

    async def test_internal_targets_are_refused_without_a_request(self):
        """SSRF guard: a client must not make the consumer call into our network or the cloud metadata service."""
        requests = []
        sender = self.sender(lambda request: requests.append(request) or httpx.Response(200))
        for url in (
            "http://127.0.0.1:5432/",
            "http://localhost/hook",
            "http://10.0.0.5/hook",
            "http://169.254.169.254/latest/meta-data",
            "http://[::1]/hook",
        ):
            with self.subTest(url=url), self.assertRaises(WebhookTargetForbiddenError):
                await sender.send(self.payment_to(url))
        self.assertEqual(requests, [])

    async def test_public_address_is_allowed(self):
        requests = []
        sender = self.sender(lambda request: requests.append(request) or httpx.Response(200))

        await sender.send(self.payment_to("http://93.184.216.34/hook"))

        self.assertEqual(len(requests), 1)

    async def test_allowed_host_may_be_internal(self):
        """docker compose sends to webhook-echo on the private network; it is allowed by name."""
        requests = []
        sender = self.sender(
            lambda request: requests.append(request) or httpx.Response(200), allowed_hosts=frozenset({"127.0.0.1"})
        )

        await sender.send(self.payment_to("http://127.0.0.1:9000/ok"))

        self.assertEqual(len(requests), 1)

    async def test_unresolvable_host_is_a_retryable_delivery_error(self):
        sender = self.sender(lambda request: httpx.Response(200), allowed_hosts=frozenset())

        with self.assertRaises(WebhookDeliveryError):
            await sender.send(self.payment_to("http://nonexistent.invalid/hook"))


class ExplodingStream(httpx.AsyncByteStream):
    async def __aiter__(self):
        raise AssertionError("response body was read")
        yield b""
