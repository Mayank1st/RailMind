from decimal import Decimal
from uuid import UUID
from datetime import datetime
from pydantic import BaseModel

from app.core.constants.payment import (
    PaymentMethod,
    PaymentStatus,
    PaymentGateway,
)


class PaymentInitiateResponse(BaseModel):
    payment_id: UUID
    booking_id: UUID
    booking_pnr: str
    amount: Decimal
    currency: str
    mock_order_id: str
    payment_status: PaymentStatus

    model_config = {"from_attributes": True}


class PaymentProcessResponse(BaseModel):
    payment_id: UUID
    booking_pnr: str
    payment_status: PaymentStatus
    payment_method: PaymentMethod | None
    booking_status: str
    paid_at: datetime | None
    failure_reason: str | None = None

    model_config = {"from_attributes": True}


class PaymentStatusResponse(BaseModel):
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

    model_config = {"from_attributes": True}
