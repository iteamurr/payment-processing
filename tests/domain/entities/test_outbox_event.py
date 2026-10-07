import unittest
import uuid

from payments_processing.domain.entities.outbox_event import PAYMENT_CREATED, OutboxEvent, PaymentCreated


class OutboxEventTest(unittest.TestCase):
    def test_payment_created_event_carries_the_message_payload(self):
        payment_id = uuid.uuid4()

        event = OutboxEvent.payment_created(payment_id)

        self.assertIsInstance(event.id, uuid.UUID)
        self.assertEqual(event.event_type, PAYMENT_CREATED)
        self.assertEqual(event.payload, PaymentCreated(payment_id).to_payload())
        self.assertIsNotNone(event.created_at.tzinfo)


class PaymentCreatedTest(unittest.TestCase):
    def test_payload_round_trip(self):
        message = PaymentCreated(uuid.uuid4())

        self.assertEqual(message.to_payload(), {"payment_id": str(message.payment_id)})
        self.assertEqual(PaymentCreated.from_payload(message.to_payload()), message)

    def test_malformed_payload_raises_value_error(self):
        for payload in ([], {}, {"payment_id": 5}, {"payment_id": None}, {"payment_id": "nope"}):
            with self.subTest(payload=payload), self.assertRaises(ValueError):
                PaymentCreated.from_payload(payload)
