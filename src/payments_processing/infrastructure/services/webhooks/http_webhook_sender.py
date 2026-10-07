from __future__ import annotations

import asyncio
from dataclasses import dataclass

import httpx

from payments_processing.domain.entities.payment import Payment
from payments_processing.domain.errors import WebhookDeliveryError
from payments_processing.domain.services.webhooks.webhook_sender import WebhookSender
from payments_processing.infrastructure.services.webhooks.serializers import WebhookPayload


@dataclass
class HttpWebhookSender(WebhookSender):
    """Redirects are not followed, so 3xx counts as a failed delivery."""

    client: httpx.AsyncClient
    timeout_s: float = 10.0

    async def send(self, payment: Payment) -> None:
        """The deadline covers the whole request (httpx timeouts are per phase); the response body is never read."""
        url = payment.webhook_url
        body = WebhookPayload.model_validate(payment).model_dump(mode="json")
        try:
            async with asyncio.timeout(self.timeout_s):
                async with self.client.stream("POST", url, json=body) as response:
                    status = response.status_code
        except TimeoutError as exc:
            raise WebhookDeliveryError(f"webhook {url}: timed out after {self.timeout_s}s") from exc
        except httpx.HTTPError as exc:
            raise WebhookDeliveryError(f"webhook {url}: {exc!r}") from exc
        if not httpx.codes.is_success(status):
            raise WebhookDeliveryError(f"webhook {url}: HTTP {status}")
