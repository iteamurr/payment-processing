import unittest
import uuid
from unittest.mock import create_autospec

from payments_processing.application.payments.payment_lookup import PaymentLookup
from payments_processing.application.payments.payment_processing import PaymentProcessing
from payments_processing.domain.entities.outbox_event import OutboxEvent
from payments_processing.domain.entities.payment import Payment, PaymentStatus
from payments_processing.domain.errors import PaymentNotFoundError, WebhookDeliveryError, WebhookTargetForbiddenError
from payments_processing.domain.services.payments.payment_gateway import PaymentGateway
from payments_processing.domain.services.webhooks.webhook_sender import WebhookSender
from tests.mocks import InMemoryPaymentRepository, payment_request


class PaymentProcessingTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.repository = InMemoryPaymentRepository()
        self.gateway = create_autospec(PaymentGateway, instance=True)
        self.gateway.charge.return_value = PaymentStatus.SUCCEEDED
        self.webhooks = create_autospec(WebhookSender, instance=True)
        self.processing = PaymentProcessing(
            PaymentLookup(self.repository), self.repository, self.gateway, self.webhooks
        )
        self.payment = Payment.build(payment_request(), "key-1")
        await self.repository.add(self.payment, OutboxEvent.payment_created(self.payment.id))

    async def test_pending_payment_is_charged_stored_and_notified(self):
        await self.processing.process(self.payment.id)

        stored = self.repository.payments[self.payment.id]
        self.assertIs(stored.status, PaymentStatus.SUCCEEDED)
        self.assertIsNotNone(stored.processed_at)
        self.gateway.charge.assert_awaited_once()
        self.webhooks.send.assert_awaited_once_with(stored)

    async def test_declined_charge_is_a_result_not_an_error(self):
        self.gateway.charge.return_value = PaymentStatus.FAILED

        await self.processing.process(self.payment.id)

        stored = self.repository.payments[self.payment.id]
        self.assertIs(stored.status, PaymentStatus.FAILED)
        self.assertIs(self.webhooks.send.await_args.args[0].status, PaymentStatus.FAILED)

    async def test_webhook_failure_propagates_after_the_status_is_stored(self):
        self.webhooks.send.side_effect = WebhookDeliveryError("HTTP 500")

        with self.assertRaises(WebhookDeliveryError):
            await self.processing.process(self.payment.id)

        self.assertIs(self.repository.payments[self.payment.id].status, PaymentStatus.SUCCEEDED)

    async def test_retry_after_webhook_failure_does_not_charge_again(self):
        self.webhooks.send.side_effect = [WebhookDeliveryError("HTTP 500"), None]
        with self.assertRaises(WebhookDeliveryError):
            await self.processing.process(self.payment.id)

        await self.processing.process(self.payment.id)

        self.gateway.charge.assert_awaited_once()
        self.assertEqual(self.webhooks.send.await_count, 2)

    async def test_lost_race_notifies_with_the_status_stored_by_the_winner(self):
        """A parallel delivery of the same message stores FAILED while this one is still charging."""

        async def charge(payment):
            winner = self.repository.payments[payment.id]
            winner.status = PaymentStatus.FAILED
            return PaymentStatus.SUCCEEDED

        self.gateway.charge.side_effect = charge

        await self.processing.process(self.payment.id)

        self.assertIs(self.repository.payments[self.payment.id].status, PaymentStatus.FAILED)
        self.assertIs(self.webhooks.send.await_args.args[0].status, PaymentStatus.FAILED)

    async def test_unknown_payment_raises(self):
        with self.assertRaises(PaymentNotFoundError):
            await self.processing.process(uuid.uuid4())
        self.webhooks.send.assert_not_awaited()

    async def test_forbidden_webhook_target_fails_the_payment_without_charging(self):
        """Charging first would take the money without telling the client; pending forever would hide the outcome."""
        self.webhooks.check_target.side_effect = WebhookTargetForbiddenError("10.0.0.5")

        with self.assertRaises(WebhookTargetForbiddenError):
            await self.processing.process(self.payment.id)

        self.gateway.charge.assert_not_awaited()
        stored = self.repository.payments[self.payment.id]
        self.assertIs(stored.status, PaymentStatus.FAILED)
        self.assertIsNotNone(stored.processed_at)
