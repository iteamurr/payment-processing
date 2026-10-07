import unittest
from decimal import Decimal

from payments_processing.application.payments.payment_creation import PaymentCreation
from payments_processing.domain.entities.payment import PaymentStatus
from payments_processing.domain.errors import IdempotencyConflictError
from payments_processing.domain.messages import PAYMENT_CREATED
from tests.mocks import InMemoryPaymentRepository, payment_request


class PaymentCreationTest(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.repository = InMemoryPaymentRepository()
        self.creation = PaymentCreation(self.repository)

    async def test_new_key_stores_a_pending_payment_with_a_payment_created_event(self):
        payment = await self.creation.create(payment_request(), "key-1")

        self.assertIs(payment.status, PaymentStatus.PENDING)
        self.assertEqual(await self.repository.get(payment.id), payment)
        self.assertEqual(len(self.repository.events), 1)
        self.assertEqual(self.repository.events[0].event_type, PAYMENT_CREATED)
        self.assertEqual(self.repository.events[0].payload, {"payment_id": str(payment.id)})

    async def test_repeated_key_with_the_same_request_returns_the_stored_payment(self):
        first = await self.creation.create(payment_request(), "key-1")
        second = await self.creation.create(payment_request(), "key-1")

        self.assertEqual(second.id, first.id)
        self.assertEqual(len(self.repository.payments), 1)
        self.assertEqual(len(self.repository.events), 1)

    async def test_repeat_returns_the_current_status(self):
        first = await self.creation.create(payment_request(), "key-1")
        stored = self.repository.payments[first.id]
        stored.status = PaymentStatus.SUCCEEDED

        second = await self.creation.create(payment_request(), "key-1")

        self.assertIs(second.status, PaymentStatus.SUCCEEDED)

    async def test_same_amount_written_differently_is_the_same_request(self):
        first = await self.creation.create(payment_request(amount=Decimal("100")), "key-1")
        second = await self.creation.create(payment_request(amount=Decimal("100.00")), "key-1")

        self.assertEqual(second.id, first.id)

    async def test_repeated_key_with_a_different_request_is_a_conflict(self):
        await self.creation.create(payment_request(), "key-1")

        with self.assertRaises(IdempotencyConflictError):
            await self.creation.create(payment_request(amount=Decimal("999.00")), "key-1")
        self.assertEqual(len(self.repository.payments), 1)
        self.assertEqual(len(self.repository.events), 1)
