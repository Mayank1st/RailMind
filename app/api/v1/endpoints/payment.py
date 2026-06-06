from uuid import UUID

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.response import APIResponse
from app.db.session import get_db
from app.api.deps import get_current_user, get_db
from app.schemas.Request.paymentRequestDTO import (
    PaymentInitiateRequest,
    PaymentProcessRequest,
)
from app.schemas.Response.paymentResponseDTO import (
    PaymentInitiateResponse,
    PaymentProcessResponse,
    PaymentStatusResponse,
)
from app.services.payment_service import PaymentService

router = APIRouter(prefix="/payments", tags=["Payments"])
service = PaymentService()


@router.post(
    "/initiate",
    response_model=APIResponse,
    status_code=status.HTTP_201_CREATED,
)
async def initiate_payment(
    request: PaymentInitiateRequest,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    payment, booking = await service.initiate_payment(request, current_user, db)
    booking_pnr = booking.pnr_number

    response = PaymentInitiateResponse(
        payment_id=payment.id,
        booking_id=payment.booking_id,
        booking_pnr=booking_pnr,
        amount=payment.amount,
        currency=payment.currency,
        mock_order_id=payment.gateway_order_id,
        payment_status=payment.payment_status,
    )
    return APIResponse(
        success=True,
        message="Payment initiated successfully",
        data=response.model_dump(mode="json"),
    )


@router.post("/process", response_model=APIResponse)
async def process_payment(
    request: PaymentProcessRequest,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    payment, booking = await service.process_payment(request, current_user, db)

    is_success = payment.payment_status.value == "SUCCESS"

    response = PaymentProcessResponse(
        payment_id=payment.id,
        booking_pnr=booking.pnr_number,
        payment_status=payment.payment_status,
        payment_method=payment.payment_method,
        booking_status=booking.booking_status,
        paid_at=payment.paid_at,
        failure_reason=payment.failure_reason,
    )
    return APIResponse(
        success=is_success,
        message=(
            "Payment successful, booking confirmed"
            if is_success
            else f"Payment failed: {payment.failure_reason}"
        ),
        data=response.model_dump(mode="json"),
    )


@router.get("/{payment_id}/status", response_model=APIResponse)
async def get_payment_status(
    payment_id: UUID,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    payment = await service.get_payment_status(payment_id, current_user, db)

    response = PaymentStatusResponse(
        payment_id=payment.id,
        booking_id=payment.booking_id,
        amount=payment.amount,
        currency=payment.currency,
        payment_status=payment.payment_status,
        payment_method=payment.payment_method,
        gateway=payment.gateway,
        paid_at=payment.paid_at,
        failed_at=payment.failed_at,
        failure_reason=payment.failure_reason,
    )
    return APIResponse(
        success=True,
        message="Payment status fetched",
        data=response.model_dump(mode="json"),
    )
