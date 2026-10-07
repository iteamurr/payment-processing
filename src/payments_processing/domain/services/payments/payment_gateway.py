from __future__ import annotations

from abc import ABC, abstractmethod

from payments_processing.domain.entities.payment import Payment, PaymentStatus


class PaymentGateway(ABC):
    @abstractmethod
    async def charge(self, payment: Payment) -> PaymentStatus:
        """Final status of the charge: SUCCEEDED or FAILED."""
