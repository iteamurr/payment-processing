import unittest
import uuid

from payments_processing.application.payments.payment_lookup import PaymentLookup
from payments_processing.domain.entities.outbox_event import OutboxEvent
from payments_processing.domain.entities.payment import Payment
from payments_processing.domain.errors import PaymentNotFoundError
from tests.mocks import InMemoryPaymentRepository, payment_request


class PaymentLookupTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.repository = InMemoryPaymentRepository()
        self.lookup = PaymentLookup(self.repository)

    async def test_returns_the_stored_payment(self):
        payment = Payment.build(payment_request(), "key-1")
        await self.repository.add(payment, OutboxEvent.payment_created(payment.id))

        self.assertEqual(await self.lookup.get(payment.id), payment)

    async def test_unknown_payment_raises(self):
        with self.assertRaises(PaymentNotFoundError):
            await self.lookup.get(uuid.uuid4())
