from __future__ import annotations

from dataclasses import dataclass

from starlette.types import ASGIApp, Message, Receive, Scope, Send

from payments_processing.presentation.api.common.errors import MAX_BODY_BYTES, RequestTooLarge


@dataclass
class BodySizeLimit:
    """Raises RequestTooLarge while the body is being read, before FastAPI has buffered all of it.

    FastAPI re-raises an HTTPException from body parsing, so the 413 is rendered like any other ApiError."""

    app: ASGIApp
    max_bytes: int = MAX_BODY_BYTES

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        received = 0

        async def limited_receive() -> Message:
            nonlocal received
            message = await receive()
            received += len(message.get("body", b""))
            if received > self.max_bytes:
                raise RequestTooLarge()
            return message

        await self.app(scope, limited_receive, send)
