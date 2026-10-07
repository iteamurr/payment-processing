from __future__ import annotations

from typing import Any, ClassVar

from fastapi import HTTPException

from payments_processing.presentation.api.common.serializers import ErrorOut


class ApiError(HTTPException):
    """HTTP error that also documents itself: status code, ErrorOut body and description come from the subclass."""

    code: ClassVar[int]
    description: ClassVar[str]

    def __init__(self) -> None:
        super().__init__(status_code=self.code, detail=self.description)


class InvalidApiKey(ApiError):
    code = 401
    description = "Missing or invalid X-API-Key"


class PaymentNotFound(ApiError):
    code = 404
    description = "Payment not found"


class IdempotencyKeyReused(ApiError):
    code = 409
    description = "Idempotency-Key reused with a different body"


MAX_BODY_BYTES = 64 * 1024


class RequestTooLarge(ApiError):
    code = 413
    description = f"Request body is larger than {MAX_BODY_BYTES // 1024} KiB"


def responses(*errors: type[ApiError]) -> dict[int | str, dict[str, Any]]:
    """OpenAPI `responses` for the errors a route or router can raise."""
    return {error.code: {"model": ErrorOut, "description": error.description} for error in errors}
