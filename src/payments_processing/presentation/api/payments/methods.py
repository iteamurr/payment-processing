from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Header, HTTPException

from payments_processing.application.payments.payment_creation import PaymentCreation
from payments_processing.domain.errors import IdempotencyConflictError
from payments_processing.domain.services.payments.payment_repository import PaymentRepository
from payments_processing.presentation.api.auth import require_api_key
from payments_processing.presentation.api.common.serializers import ErrorOut
from payments_processing.presentation.api.deps import resolve_depends
from payments_processing.presentation.api.payments.serializers import CreatePaymentIn, PaymentAcceptedOut, PaymentOut

router = APIRouter(
    prefix="/api/v1/payments",
    tags=["payments"],
    dependencies=[Depends(require_api_key)],
    responses={401: {"model": ErrorOut, "description": "Missing or invalid X-API-Key"}},
)


@router.post(
    "",
    operation_id="create_payment",
    status_code=202,
    response_model=PaymentAcceptedOut,
    responses={409: {"model": ErrorOut, "description": "Idempotency-Key reused with a different body"}},
)
async def create_payment(
    body: CreatePaymentIn,
    idempotency_key: str = Header(alias="Idempotency-Key", min_length=1, max_length=255),
    creation: PaymentCreation = resolve_depends(PaymentCreation),
) -> PaymentAcceptedOut:
    """A repeated Idempotency-Key with the same body returns the stored payment."""
    try:
        payment = await creation.create(body.to_request(), idempotency_key)
    except IdempotencyConflictError:
        raise HTTPException(status_code=409, detail="idempotency key reused with a different request") from None
    return PaymentAcceptedOut(payment_id=payment.id, status=payment.status, created_at=payment.created_at)


@router.get(
    "/{payment_id}",
    operation_id="get_payment",
    response_model=PaymentOut,
    responses={404: {"model": ErrorOut, "description": "Payment not found"}},
)
async def get_payment(
    payment_id: uuid.UUID,
    repository: PaymentRepository = resolve_depends(PaymentRepository),
) -> PaymentOut:
    payment = await repository.get(payment_id)
    if payment is None:
        raise HTTPException(status_code=404, detail="payment not found")
    return PaymentOut.model_validate(payment)
