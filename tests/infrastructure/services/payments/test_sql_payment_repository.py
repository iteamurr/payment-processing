import uuid
from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy import select

from payments_processing.domain.entities.outbox_event import OutboxEvent
from payments_processing.domain.entities.payment import Payment, PaymentStatus
from payments_processing.infrastructure.db.models import OutboxRow
from payments_processing.infrastructure.services.payments.sql_payment_repository import SqlPaymentRepository
from tests.infrastructure.db import DatabaseTestCase
from tests.mocks import payment_request


class SqlPaymentRepositoryTest(DatabaseTestCase):
    async def asyncSetUp(self):
        await super().asyncSetUp()
        self.repository = SqlPaymentRepository(self.sessions)
        self.payment = Payment.build(payment_request(metadata={"order": {"id": 1}, "note": "привет"}), "key-1")
        self.event = OutboxEvent.payment_created(self.payment.id)

    async def outbox_rows(self) -> list[OutboxRow]:
        async with self.sessions() as session:
            return list(await session.scalars(select(OutboxRow)))

    async def test_add_round_trips_every_field(self):
        self.assertTrue(await self.repository.add(self.payment, self.event))

        self.assertEqual(await self.repository.get(self.payment.id), self.payment)
        self.assertEqual(await self.repository.get_by_idempotency_key("key-1"), self.payment)

    async def test_add_stores_the_outbox_event_with_the_payment(self):
        await self.repository.add(self.payment, self.event)

        [row] = await self.outbox_rows()
        self.assertEqual(row.id, self.event.id)
        self.assertEqual(row.event_type, self.event.event_type)
        self.assertEqual(row.payload, self.event.payload)
        self.assertIsNone(row.published_at)

    async def test_taken_idempotency_key_adds_nothing(self):
        await self.repository.add(self.payment, self.event)
        duplicate = Payment.build(payment_request(amount=Decimal("1.00")), "key-1")

        self.assertFalse(await self.repository.add(duplicate, OutboxEvent.payment_created(duplicate.id)))
        self.assertIsNone(await self.repository.get(duplicate.id))
        self.assertEqual(len(await self.outbox_rows()), 1)

    async def test_unknown_lookups_return_none(self):
        self.assertIsNone(await self.repository.get(uuid.uuid4()))
        self.assertIsNone(await self.repository.get_by_idempotency_key("missing"))

    async def test_save_result_completes_a_pending_payment_once(self):
        await self.repository.add(self.payment, self.event)
        first = await self.repository.get(self.payment.id)
        second = await self.repository.get(self.payment.id)
        first.complete(PaymentStatus.SUCCEEDED, datetime.now(UTC))
        second.complete(PaymentStatus.FAILED, datetime.now(UTC))

        self.assertTrue(await self.repository.save_result(first))
        self.assertFalse(await self.repository.save_result(second))

        stored = await self.repository.get(self.payment.id)
        self.assertIs(stored.status, PaymentStatus.SUCCEEDED)
        self.assertEqual(stored.processed_at, first.processed_at)
