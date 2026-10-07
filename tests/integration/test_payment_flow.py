import asyncio
import json
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import httpx
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from payments_processing.application.outbox.outbox_relay import OutboxRelay
from payments_processing.application.payments.payment_creation import PaymentCreation
from payments_processing.application.payments.payment_processing import PaymentProcessing
from payments_processing.domain.entities.payment import PaymentStatus
from payments_processing.infrastructure.broker.rabbit import (
    ATTEMPT_HEADER,
    PAYMENTS_NEW,
    PAYMENTS_NEW_DLQ,
    RETRY_QUEUES,
    build_broker,
    declare_topology,
)
from payments_processing.infrastructure.db.models import OutboxRow
from payments_processing.infrastructure.services.outbox.rabbit_event_publisher import RabbitEventPublisher
from payments_processing.infrastructure.services.outbox.sql_outbox_repository import SqlOutboxRepository
from payments_processing.infrastructure.services.payments.fake_payment_gateway import FakePaymentGateway
from payments_processing.infrastructure.services.payments.http_webhook_sender import HttpWebhookSender
from payments_processing.infrastructure.services.payments.sql_payment_repository import SqlPaymentRepository
from payments_processing.presentation.consumer.app import subscribe
from payments_processing.presentation.consumer.handler import PaymentCreatedHandler
from tests.infrastructure.broker.test_rabbit import RABBITMQ_URL
from tests.infrastructure.db import DATABASE_URL, migrate
from tests.mocks import payment_request


def webhook_receiver(calls: list[tuple[str, dict]]) -> type[BaseHTTPRequestHandler]:
    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            calls.append((self.path, body))
            self.send_response(500 if self.path.startswith("/fail") else 200)
            self.send_header("Content-Length", "0")
            self.end_headers()

        def log_message(self, *args):
            pass

    return Handler


async def eventually(check, timeout: float):
    async with asyncio.timeout(timeout):
        while not (result := await check()):
            await asyncio.sleep(0.1)
    return result


@unittest.skipUnless(DATABASE_URL and RABBITMQ_URL, "DATABASE_URL and RABBITMQ_URL are not set")
class PaymentFlowTest(unittest.IsolatedAsyncioTestCase):
    """Real Postgres and RabbitMQ with an in-process consumer.

    Run with only `postgres` and `rabbitmq` from compose: a running compose consumer would take the messages."""

    @classmethod
    def setUpClass(cls):
        migrate()

    async def asyncSetUp(self):
        engine = create_async_engine(DATABASE_URL)
        self.addAsyncCleanup(engine.dispose)
        async with engine.begin() as connection:
            await connection.execute(text("TRUNCATE payments, outbox"))
        self.sessions = async_sessionmaker(engine, expire_on_commit=False)

        self.calls: list[tuple[str, dict]] = []
        server = ThreadingHTTPServer(("127.0.0.1", 0), webhook_receiver(self.calls))
        threading.Thread(target=server.serve_forever, daemon=True).start()
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        self.webhook_base = f"http://127.0.0.1:{server.server_port}"

        client = httpx.AsyncClient()
        self.addAsyncCleanup(client.aclose)
        self.repository = SqlPaymentRepository(self.sessions)
        gateway = FakePaymentGateway(min_delay_s=0, max_delay_s=0, success_rate=1.0)
        processing = PaymentProcessing(self.repository, gateway, HttpWebhookSender(client, timeout_s=5))

        self.broker = build_broker(RABBITMQ_URL)
        subscribe(self.broker, PaymentCreatedHandler(processing, self.broker))
        await self.broker.connect()
        await declare_topology(self.broker)
        for queue in (PAYMENTS_NEW, PAYMENTS_NEW_DLQ, *RETRY_QUEUES):
            await (await self.broker.declare_queue(queue)).purge()
        await self.broker.start()
        self.addAsyncCleanup(self.broker.stop)

        self.creation = PaymentCreation(self.repository)
        self.relay = OutboxRelay(SqlOutboxRepository(self.sessions), RabbitEventPublisher(self.broker))

    async def test_created_payment_is_charged_stored_and_notified(self):
        payment = await self.creation.create(payment_request(webhook_url=f"{self.webhook_base}/ok"), "it-ok")

        self.assertEqual(await self.relay.publish_pending(), 1)

        async def notified():
            return len(self.calls) == 1

        await eventually(notified, timeout=10)
        path, body = self.calls[0]
        self.assertEqual(path, "/ok")
        self.assertEqual((body["payment_id"], body["status"]), (str(payment.id), "succeeded"))
        stored = await self.repository.get(payment.id)
        self.assertIs(stored.status, PaymentStatus.SUCCEEDED)
        self.assertIsNotNone(stored.processed_at)
        async with self.sessions() as session:
            self.assertIsNotNone((await session.scalar(select(OutboxRow))).published_at)

    async def test_webhook_failing_on_every_attempt_lands_in_the_dlq(self):
        payment = await self.creation.create(payment_request(webhook_url=f"{self.webhook_base}/fail"), "it-fail")
        await self.relay.publish_pending()
        dlq = await self.broker.declare_queue(PAYMENTS_NEW_DLQ)

        async def dead_lettered():
            return await dlq.get(no_ack=True, fail=False)

        message = await eventually(dead_lettered, timeout=20)

        self.assertEqual(json.loads(message.body), {"payment_id": str(payment.id)})
        self.assertEqual(message.headers[ATTEMPT_HEADER], 3)
        self.assertEqual(len(self.calls), 3)
        self.assertIs((await self.repository.get(payment.id)).status, PaymentStatus.SUCCEEDED)
