from decimal import Decimal
from uuid import UUID
from datetime import datetime

from app.domain.payment.constants.payment import (
    PaymentMethod,
    PaymentStatus,
    PaymentGateway,
)
from app.schemas.base import BaseDTO


# -- PaymentInitiateResponse ---------------------------------
class PaymentInitiateResponseDTO(BaseDTO):
    payment_id: UUID
    booking_id: UUID
    booking_pnr: str
    amount: Decimal
    currency: str
    mock_order_id: str
    payment_status: PaymentStatus


# -- PaymentProcessResponse ----------------------------------
class PaymentProcessResponseDTO(BaseDTO):
    payment_id: UUID
    booking_pnr: str
    payment_status: PaymentStatus
    payment_method: PaymentMethod | None
    booking_status: str
    paid_at: datetime | None
    failure_reason: str | None = None


# -- PaymentStatusResponse -----------------------------------
class PaymentStatusResponseDTO(BaseDTO):
    payment_id: UUID
    booking_id: UUID
    amount: Decimal
    currency: str
    payment_status: PaymentStatus
    payment_method: PaymentMethod | None
    gateway: PaymentGateway
    paid_at: datetime | None
    failed_at: datetime | None
    failure_reason: str | None
