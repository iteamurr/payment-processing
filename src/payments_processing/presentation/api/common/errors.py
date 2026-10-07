from __future__ import annotations

import math
from typing import Any, ClassVar, cast

from fastapi import HTTPException, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from payments_processing.presentation.api.common.serializers import ErrorOut


def _json_safe(value: object) -> object:
    """Makes invalid input embedded in a validation error safe for a standards-compliant JSON response."""
    if isinstance(value, float) and not math.isfinite(value):
        return str(value)
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in cast(dict[object, object], value).items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(item) for item in cast(list[object] | tuple[object, ...], value)]
    return value


async def request_validation_error(_request: Request, error: RequestValidationError) -> JSONResponse:
    """Renders 422 even when the rejected input contains non-standard NaN or Infinity values."""
    return JSONResponse(status_code=422, content={"detail": jsonable_encoder(_json_safe(error.errors()))})


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
