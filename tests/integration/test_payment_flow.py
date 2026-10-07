import asyncio
import json
import threading
import unittest
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

import httpx
from sqlalchemy import select, text

from payments_processing.application.outbox.outbox_relay import OutboxRelay
from payments_processing.application.payments.payment_creation import PaymentCreation
from payments_processing.application.payments.payment_lookup import PaymentLookup
from payments_processing.application.payments.payment_processing import PaymentProcessing
from payments_processing.domain.entities.payment import Payment, PaymentStatus
from payments_processing.infrastructure.broker.client import build_broker
from payments_processing.infrastructure.broker.retry import ATTEMPT_HEADER
from payments_processing.infrastructure.broker.topology import (
    PAYMENTS_NEW,
    PAYMENTS_NEW_DLQ,
    RETRY_QUEUES,
    declare_topology,
)
from payments_processing.infrastructure.db.models import OutboxRow
from payments_processing.infrastructure.db.session import build_engine, build_sessionmaker
from payments_processing.infrastructure.services.outbox.rabbit_event_publisher import RabbitEventPublisher
from payments_processing.infrastructure.services.outbox.sql_outbox_repository import SqlOutboxRepository
from payments_processing.infrastructure.services.payments.fake_payment_gateway import FakePaymentGateway
from payments_processing.infrastructure.services.payments.sql_payment_repository import SqlPaymentRepository
from payments_processing.infrastructure.services.webhooks.http_webhook_sender import HttpWebhookSender
from payments_processing.presentation.consumer.app import subscribe
from payments_processing.presentation.consumer.handler import PaymentCreatedHandler
from tests.live_services import DATABASE_URL, RABBITMQ_URL, migrate, requires_database, requires_rabbitmq
from tests.mocks import payment_request


def webhook_receiver(calls: list[tuple[str, dict]]) -> type[BaseHTTPRequestHandler]:
    """Records every POST; paths starting with /fail answer 500."""

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            calls.append((self.path, body))
            self.send_response(500 if self.path.startswith("/fail") else 200)
            self.send_header("Content-Length", "0")
            self.end_headers()

        def log_message(self, format: str, *args: Any) -> None:
            pass

    return Handler


async def eventually(check, timeout: float):
    async with asyncio.timeout(timeout):
        while not (result := await check()):
            await asyncio.sleep(0.1)
    return result


@requires_database
@requires_rabbitmq
class PaymentFlowTest(unittest.IsolatedAsyncioTestCase):
    """Real Postgres and RabbitMQ with an in-process consumer.

    Run with compose api and consumer stopped: they would take the outbox rows and messages."""

    @classmethod
    def setUpClass(cls):
        migrate()

    async def asyncSetUp(self):
        engine = build_engine(DATABASE_URL)
        self.addAsyncCleanup(engine.dispose)
        async with engine.begin() as connection:
            await connection.execute(text("TRUNCATE payments, outbox"))
        self.sessions = build_sessionmaker(engine)
        self.repository = SqlPaymentRepository(self.sessions)
        self.calls: list[tuple[str, dict]] = []
        self.webhook_base = self.start_webhook_receiver()
        self.broker = await self.start_consumer()
        self.creation = PaymentCreation(self.repository)
        self.relay = OutboxRelay(SqlOutboxRepository(self.sessions), RabbitEventPublisher(self.broker))

    def start_webhook_receiver(self) -> str:
        server = ThreadingHTTPServer(("127.0.0.1", 0), webhook_receiver(self.calls))
        threading.Thread(target=server.serve_forever, daemon=True).start()
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        return f"http://127.0.0.1:{server.server_port}"

    async def start_consumer(self):
        client = httpx.AsyncClient()
        self.addAsyncCleanup(client.aclose)
        gateway = FakePaymentGateway(min_delay_s=0, max_delay_s=0, success_rate=1.0)
        sender = HttpWebhookSender(client, secret="webhook-secret", timeout_s=5, allowed_hosts=frozenset({"127.0.0.1"}))
        processing = PaymentProcessing(PaymentLookup(self.repository), self.repository, gateway, sender)

        broker = build_broker(RABBITMQ_URL, prefetch_count=1)
        subscribe(broker, PaymentCreatedHandler(processing, broker))
        await broker.connect()
        await declare_topology(broker)
        for queue in (PAYMENTS_NEW, PAYMENTS_NEW_DLQ, *RETRY_QUEUES):
            await (await broker.declare_queue(queue)).purge()
        await broker.start()
        self.addAsyncCleanup(broker.stop)
        return broker

    async def stored(self, payment_id: uuid.UUID) -> Payment:
        payment = await self.repository.get(payment_id)
        assert payment is not None
        return payment

    async def test_created_payment_is_charged_stored_and_notified(self):
        payment = await self.creation.create(payment_request(webhook_url=f"{self.webhook_base}/ok"), "it-ok")

        self.assertEqual(await self.relay.publish_pending(), 1)

        async def notified():
            return len(self.calls) == 1

        await eventually(notified, timeout=10)
        path, body = self.calls[0]
        self.assertEqual(path, "/ok")
        self.assertEqual((body["payment_id"], body["status"]), (str(payment.id), "succeeded"))
        stored = await self.stored(payment.id)
        self.assertIs(stored.status, PaymentStatus.SUCCEEDED)
        self.assertIsNotNone(stored.processed_at)
        async with self.sessions() as session:
            self.assertIsNotNone((await session.scalars(select(OutboxRow))).one().published_at)

    async def test_webhook_failing_on_every_attempt_lands_in_the_dlq(self):
        payment = await self.creation.create(payment_request(webhook_url=f"{self.webhook_base}/fail"), "it-fail")
        await self.relay.publish_pending()
        dlq = await self.broker.declare_queue(PAYMENTS_NEW_DLQ)

        async def dead_lettered():
            return await dlq.get(no_ack=True, fail=False)

        message = await eventually(dead_lettered, timeout=60)

        self.assertEqual(json.loads(message.body), {"payment_id": str(payment.id)})
        self.assertEqual(message.headers[ATTEMPT_HEADER], 3)
        self.assertEqual(len(self.calls), 3)
        self.assertIs((await self.stored(payment.id)).status, PaymentStatus.SUCCEEDED)
