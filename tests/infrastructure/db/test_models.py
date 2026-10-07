import unittest
import uuid
from datetime import UTC, datetime

from payments_processing.domain.entities.outbox_event import OutboxEvent
from payments_processing.domain.entities.payment import Payment, PaymentStatus
from payments_processing.infrastructure.db.models import OutboxRow, PaymentRow
from tests.mocks import payment_request


class PaymentRowTest(unittest.TestCase):
    def test_insert_values_and_back_round_trip_every_field(self):
        payment = Payment.build(payment_request(metadata={"note": "привет"}), "key-1")
        payment.complete(PaymentStatus.SUCCEEDED, datetime(2026, 10, 7, 12, 0, tzinfo=UTC))

        self.assertEqual(PaymentRow(**PaymentRow.insert_values(payment)).to_payment(), payment)

    def test_insert_values_use_column_types(self):
        payment = Payment.build(payment_request(), "key-1")

        values = PaymentRow.insert_values(payment)

        self.assertEqual(
            (values["amount"], values["currency"], values["status"]), (payment.money.amount, "RUB", "pending")
        )
        self.assertEqual(values["meta"], payment.metadata)


class OutboxRowTest(unittest.TestCase):
    def test_event_round_trip(self):
        event = OutboxEvent.payment_created(uuid.uuid4())

        row = OutboxRow.from_event(event)

        self.assertIsNone(row.published_at)
        self.assertEqual(row.to_event(), event)
