import unittest
import uuid
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from payments_processing.domain.entities.payment import Payment, PaymentStatus
from payments_processing.domain.errors import InvalidPaymentTransitionError
from payments_processing.domain.values.money import Currency
from tests.mocks import payment_request


class PaymentRequestFingerprintTest(unittest.TestCase):
    def test_fingerprint_is_sha256_hex(self):
        fingerprint = payment_request().fingerprint()

        self.assertEqual(len(fingerprint), 64)
        int(fingerprint, 16)

    def test_fingerprint_ignores_amount_formatting(self):
        self.assertEqual(
            payment_request(amount=Decimal("100")).fingerprint(),
            payment_request(amount=Decimal("100.00")).fingerprint(),
        )

    def test_fingerprint_ignores_metadata_key_order(self):
        self.assertEqual(
            payment_request(metadata={"a": 1, "b": 2}).fingerprint(),
            payment_request(metadata={"b": 2, "a": 1}).fingerprint(),
        )

    def test_fingerprint_changes_with_any_field(self):
        base = payment_request().fingerprint()
        changes: tuple[dict[str, Any], ...] = (
            {"amount": Decimal("100.51")},
            {"currency": Currency.USD},
            {"description": "Order #2"},
            {"metadata": {}},
            {"webhook_url": "http://hooks.example/other"},
        )
        for change in changes:
            with self.subTest(change=change):
                self.assertNotEqual(payment_request(**change).fingerprint(), base)


class PaymentTest(unittest.TestCase):
    def test_build_creates_a_pending_payment_with_the_request_fingerprint(self):
        request = payment_request()

        payment = Payment.build(request, "key-1")

        self.assertIsInstance(payment.id, uuid.UUID)
        self.assertIs(payment.status, PaymentStatus.PENDING)
        self.assertEqual(payment.money, request.money)
        self.assertEqual(payment.idempotency_key, "key-1")
        self.assertEqual(payment.request_hash, request.fingerprint())
        self.assertIsNotNone(payment.created_at.tzinfo)
        self.assertIsNone(payment.processed_at)

    def test_build_does_not_share_metadata_with_the_request(self):
        """PaymentRequest is frozen but its dict is not; the payment must not change when the caller's dict does."""
        request = payment_request(metadata={"order": {"id": 1}})
        payment = Payment.build(request, "key-1")

        request.metadata["order"]["id"] = 2
        request.metadata["extra"] = True

        self.assertEqual(payment.metadata, {"order": {"id": 1}})

    def test_pending_payment_completes_to_either_final_status(self):
        processed_at = datetime(2026, 10, 7, 12, 0, tzinfo=UTC)
        for status in (PaymentStatus.SUCCEEDED, PaymentStatus.FAILED):
            with self.subTest(status=status):
                payment = Payment.build(payment_request(), "key-1")

                payment.complete(status, processed_at)

                self.assertIs(payment.status, status)
                self.assertEqual(payment.processed_at, processed_at)

    def test_completed_payment_cannot_change_status_again(self):
        payment = Payment.build(payment_request(), "key-1")
        payment.complete(PaymentStatus.SUCCEEDED, datetime.now(UTC))

        with self.assertRaises(InvalidPaymentTransitionError):
            payment.complete(PaymentStatus.FAILED, datetime.now(UTC))
        self.assertIs(payment.status, PaymentStatus.SUCCEEDED)

    def test_pending_is_not_a_completion_status(self):
        payment = Payment.build(payment_request(), "key-1")

        with self.assertRaises(InvalidPaymentTransitionError):
            payment.complete(PaymentStatus.PENDING, datetime.now(UTC))
