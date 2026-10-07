from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import httpx

from payments_processing.domain.errors import WebhookDeliveryError
from payments_processing.domain.services.payments.webhook_sender import WebhookSender


@dataclass
class HttpWebhookSender(WebhookSender):
    """Redirects are not followed, so 3xx counts as a failed delivery."""

    client: httpx.AsyncClient
    timeout_s: float = 10.0

    async def send(self, url: str, payload: dict[str, Any]) -> None:
        try:
            response = await self.client.post(url, json=payload, timeout=self.timeout_s)
        except httpx.HTTPError as exc:
            raise WebhookDeliveryError(f"webhook {url}: {exc!r}") from exc
        if not response.is_success:
            raise WebhookDeliveryError(f"webhook {url}: HTTP {response.status_code}")
