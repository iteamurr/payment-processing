import unittest
import uuid

from payments_processing.domain.entities.outbox_event import PAYMENT_CREATED, OutboxEvent


class OutboxEventTest(unittest.TestCase):
    def test_payment_created_carries_only_the_payment_id(self):
        payment_id = uuid.uuid4()

        event = OutboxEvent.payment_created(payment_id)

        self.assertIsInstance(event.id, uuid.UUID)
        self.assertEqual(event.event_type, PAYMENT_CREATED)
        self.assertEqual(event.payload, {"payment_id": str(payment_id)})
        self.assertIsNotNone(event.created_at.tzinfo)
