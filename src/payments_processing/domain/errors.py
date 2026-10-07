from __future__ import annotations


class PaymentNotFoundError(LookupError):
    """No payment with the given id."""


class IdempotencyConflictError(ValueError):
    """Idempotency-Key reused with a different request body."""


class InvalidPaymentTransitionError(ValueError):
    """Illegal Payment status transition."""


class WebhookDeliveryError(Exception):
    """Webhook endpoint did not accept the notification."""


class InvalidAmountError(ValueError):
    """Amount is not positive or has more than 2 decimal places."""


class WebhookTargetForbiddenError(Exception):
    """webhook_url resolves to a loopback, private or otherwise non-public address."""
