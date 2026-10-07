from __future__ import annotations

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
            response = await self.client.post(url, json=_payload(payment), timeout=self.timeout_s)
        except httpx.HTTPError as exc:
            raise WebhookDeliveryError(f"webhook {url}: {exc!r}") from exc
        if not response.is_success:
            raise WebhookDeliveryError(f"webhook {url}: HTTP {response.status_code}")


def _payload(payment: Payment) -> dict[str, Any]:
    return {
        "payment_id": str(payment.id),
        "status": payment.status.value,
        "amount": str(payment.amount),
        "currency": payment.currency.value,
        "processed_at": payment.processed_at.isoformat() if payment.processed_at else None,
    }
