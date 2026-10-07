from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any

import httpx

from payments_processing.domain.entities.payment import Payment
from payments_processing.domain.errors import WebhookDeliveryError
from payments_processing.domain.services.payments.webhook_sender import WebhookSender


@dataclass
class HttpWebhookSender(WebhookSender):
    """Redirects are not followed, so 3xx counts as a failed delivery."""

    client: httpx.AsyncClient
    timeout_s: float = 10.0

    async def send(self, payment: Payment) -> None:
        url = payment.webhook_url
        try:
            # total deadline: httpx timeouts are per phase; the body is never read, only the status
            async with asyncio.timeout(self.timeout_s):
                async with self.client.stream("POST", url, json=_payload(payment)) as response:
                    status = response.status_code
        except TimeoutError as exc:
            raise WebhookDeliveryError(f"webhook {url}: timed out after {self.timeout_s}s") from exc
        except httpx.HTTPError as exc:
            raise WebhookDeliveryError(f"webhook {url}: {exc!r}") from exc
        if not httpx.codes.is_success(status):
            raise WebhookDeliveryError(f"webhook {url}: HTTP {status}")


def _payload(payment: Payment) -> dict[str, Any]:
    return {
        "payment_id": str(payment.id),
        "status": payment.status.value,
        "amount": str(payment.money.amount),
        "currency": payment.money.currency.value,
        "processed_at": payment.processed_at.isoformat() if payment.processed_at else None,
    }
