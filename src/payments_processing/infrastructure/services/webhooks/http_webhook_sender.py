from __future__ import annotations

import asyncio
import hashlib
import hmac
import ipaddress
import socket
import time
from collections.abc import Set
from dataclasses import dataclass, field

import httpx

from payments_processing.domain.entities.payment import Payment
from payments_processing.domain.errors import WebhookDeliveryError, WebhookTargetForbiddenError
from payments_processing.domain.services.webhooks.webhook_sender import WebhookSender
from payments_processing.domain.webhooks import normalize_host
from payments_processing.infrastructure.services.webhooks.serializers import WebhookPayload


def _redact_url(url: str | httpx.URL) -> str:
    """Keeps the target useful in logs without leaking credentials, query parameters or fragments."""
    return str(httpx.URL(url).copy_with(username=None, password=None, query=None, fragment=None))


@dataclass
class HttpWebhookSender(WebhookSender):
    """Signs each webhook with HMAC-SHA256 over "{timestamp}.{body}"; redirects are not followed, so 3xx fails.

    Refuses targets that resolve to non-public addresses unless their host is in allowed_hosts. The check runs
    before httpx resolves the name again, so DNS rebinding between the two lookups is not covered."""

    client: httpx.AsyncClient
    secret: str
    timeout_s: float = 10.0
    allowed_hosts: Set[str] = field(default_factory=frozenset[str])

    async def send(self, payment: Payment) -> None:
        """The deadline covers the whole request (httpx timeouts are per phase); the response body is never read."""
        url = payment.webhook_url
        safe_url = _redact_url(url)
        body = WebhookPayload.model_validate(payment).model_dump_json().encode()
        try:
            async with asyncio.timeout(self.timeout_s):
                await self.check_target(payment)
                async with self.client.stream("POST", url, content=body, headers=self._headers(body)) as response:
                    status = response.status_code
        except TimeoutError as exc:
            raise WebhookDeliveryError(f"webhook {safe_url}: timed out after {self.timeout_s}s") from exc
        except httpx.HTTPError as exc:
            raise WebhookDeliveryError(f"webhook {safe_url}: {type(exc).__name__}") from None
        if not httpx.codes.is_success(status):
            raise WebhookDeliveryError(f"webhook {safe_url}: HTTP {status}")

    async def check_target(self, payment: Payment) -> None:
        """Also raises WebhookDeliveryError while the host cannot be resolved in time, which is worth retrying."""
        url = httpx.URL(payment.webhook_url)
        safe_url = _redact_url(url)
        if normalize_host(url.host) in self.allowed_hosts:
            return
        port = url.port or (443 if url.scheme == "https" else 80)
        try:
            async with asyncio.timeout(self.timeout_s):
                addresses = await asyncio.get_running_loop().getaddrinfo(url.host, port, type=socket.SOCK_STREAM)
        except (OSError, TimeoutError) as exc:
            raise WebhookDeliveryError(f"webhook {safe_url}: cannot resolve {url.host}: {type(exc).__name__}") from None
        for *_, sockaddr in addresses:
            address = ipaddress.ip_address(str(sockaddr[0]).split("%")[0])
            if not address.is_global:
                raise WebhookTargetForbiddenError(
                    f"webhook {safe_url}: {url.host} resolves to non-public {address}"
                )

    def _headers(self, body: bytes) -> dict[str, str]:
        timestamp = str(int(time.time()))
        signature = hmac.new(self.secret.encode(), f"{timestamp}.".encode() + body, hashlib.sha256).hexdigest()
        return {
            "Content-Type": "application/json",
            "X-Webhook-Timestamp": timestamp,
            "X-Webhook-Signature": f"sha256={signature}",
        }
