import unittest
import uuid

from payments_processing.domain.entities.outbox_event import OutboxEvent
from payments_processing.domain.messages import PAYMENT_CREATED, PaymentCreated


class OutboxEventTest(unittest.TestCase):
    def test_payment_created_event_carries_the_message_payload(self):
        payment_id = uuid.uuid4()

        event = OutboxEvent.payment_created(payment_id)

        self.assertIsInstance(event.id, uuid.UUID)
        self.assertEqual(event.event_type, PAYMENT_CREATED)
        self.assertEqual(event.payload, PaymentCreated(payment_id).to_payload())
        self.assertIsNotNone(event.created_at.tzinfo)
