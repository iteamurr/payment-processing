from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Header
from fastapi.exceptions import RequestValidationError

from payments_processing.application.payments.payment_creation import PaymentCreation
from payments_processing.application.payments.payment_lookup import PaymentLookup
from payments_processing.domain.errors import IdempotencyConflictError, PaymentNotFoundError
from payments_processing.presentation.api.auth import require_api_key
from payments_processing.presentation.api.common.errors import (
    IdempotencyKeyReused,
    InvalidApiKey,
    PaymentNotFound,
    RequestTooLarge,
    responses,
)
from payments_processing.presentation.api.deps import resolve_depends
from payments_processing.presentation.api.payments.serializers import (
    CreatePaymentIn,
    PaymentAcceptedOut,
    PaymentOut,
    is_internal_host,
)
from payments_processing.project.config import Config

router = APIRouter(
    prefix="/api/v1/payments",
    tags=["payments"],
    dependencies=[Depends(require_api_key)],
    responses=responses(InvalidApiKey),
)


@router.post(
    "",
    operation_id="create_payment",
    status_code=202,
    response_model=PaymentAcceptedOut,
    responses=responses(IdempotencyKeyReused, RequestTooLarge),
)
async def create_payment(
    body: CreatePaymentIn,
    idempotency_key: str = Header(alias="Idempotency-Key", min_length=1, max_length=255),
    creation: PaymentCreation = resolve_depends(PaymentCreation),
    config: Config = resolve_depends(Config),
) -> PaymentAcceptedOut:
    """A repeated Idempotency-Key with the same body returns the stored payment."""
    if is_internal_host(body.webhook_url, config.webhook_allowed_hosts):
        raise RequestValidationError(
            [
                {
                    "type": "value_error",
                    "loc": ("body", "webhook_url"),
                    "msg": "webhook_url must not point to an internal address",
                    "input": str(body.webhook_url),
                }
            ]
        )
    try:
        payment = await creation.create(body.to_request(), idempotency_key)
    except IdempotencyConflictError:
        raise IdempotencyKeyReused() from None
    return PaymentAcceptedOut.model_validate(payment)


@router.get(
    "/{payment_id}",
    operation_id="get_payment",
    response_model=PaymentOut,
    responses=responses(PaymentNotFound),
)
async def get_payment(
    payment_id: uuid.UUID,
    lookup: PaymentLookup = resolve_depends(PaymentLookup),
) -> PaymentOut:
    try:
        payment = await lookup.get(payment_id)
    except PaymentNotFoundError:
        raise PaymentNotFound() from None
    return PaymentOut.model_validate(payment)
