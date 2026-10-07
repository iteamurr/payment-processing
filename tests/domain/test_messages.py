import unittest
import uuid

from payments_processing.domain.messages import PaymentCreated


class PaymentCreatedTest(unittest.TestCase):
    def test_payload_round_trip(self):
        message = PaymentCreated(uuid.uuid4())

        self.assertEqual(message.to_payload(), {"payment_id": str(message.payment_id)})
        self.assertEqual(PaymentCreated.from_payload(message.to_payload()), message)

    def test_malformed_payload_raises_value_error(self):
        for payload in ([], {}, {"payment_id": 5}, {"payment_id": None}, {"payment_id": "nope"}):
            with self.subTest(payload=payload), self.assertRaises(ValueError):
                PaymentCreated.from_payload(payload)
