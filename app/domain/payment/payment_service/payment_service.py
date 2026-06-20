import uuid
from datetime import datetime, timezone
from decimal import Decimal

from fastapi import status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.config import settings
from app.domain.payment.constants.payment import (
    PaymentGateway,
    PaymentMethod,
    PaymentStatus,
)
from app.core.exceptions import RailMindException
from app.db.models.booking import Bookings
from app.db.models.payment import Payments
from app.domain.booking.constants.booking import BookingStatus
from app.domain.payment.dto.payment_request_dto import (
    PaymentInitiateRequestDTO,
    PaymentProcessRequestDTO,
)
from app.domain.booking.booking_service.booking_service import booking_service
from app.tasks.notification_tasks import task_send_booking_confirmation


class PaymentService:

    async def initiate_payment(
        self,
        request: PaymentInitiateRequestDTO,
        current_user: dict,
        db: AsyncSession,
    ) -> tuple[Payments, Bookings]:
        user_id = current_user.get("sub")

        # ── Booking fetch + validate ───────────────────────────────────────
        result = await db.execute(
            select(Bookings).where(Bookings.id == request.booking_id)
        )
        booking = result.scalar_one_or_none()

        if not booking:
            raise RailMindException(
                code="RM-BKG-006",
                message="Booking not found",
                status_code=status.HTTP_404_NOT_FOUND,
            )

        if str(booking.user_id) != str(user_id):
            raise RailMindException(
                code="RM-AUTH-005",
                message="Booking does not belong to current user",
                status_code=status.HTTP_403_FORBIDDEN,
            )

        # Existing bookings are currently created in confirmed/rac/waitlisted state.
        # Keep initiate flow compatible with that lifecycle while also supporting
        # initiated/payment_pending for future strict pay-first workflows.
        payable_booking_statuses = (
            BookingStatus.CONFIRMED,
            BookingStatus.RAC,
            BookingStatus.WAITLISTED,
            BookingStatus.INITIATED,
            BookingStatus.PAYMENT_PENDING,
        )
        if booking.booking_status not in payable_booking_statuses:
            raise RailMindException(
                code="RM-PAY-005",
                message=f"Booking not in payable state (current: {booking.booking_status})",
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            )

        # Prevent duplicate payment orders for the same booking.
        existing_payment_result = await db.execute(
            select(Payments).where(
                Payments.booking_id == booking.id,
                Payments.payment_status.in_(
                    [
                        PaymentStatus.PENDING,
                        PaymentStatus.PROCESSING,
                        PaymentStatus.SUCCESS,
                    ]
                ),
            )
        )
        existing_payment = existing_payment_result.scalar_one_or_none()
        if existing_payment:
            if existing_payment.payment_status == PaymentStatus.SUCCESS:
                raise RailMindException(
                    code="RM-PAY-004",
                    message="Payment already successful for this booking",
                    status_code=status.HTTP_409_CONFLICT,
                )
            raise RailMindException(
                code="RM-PAY-009",
                message="Payment is already initiated for this booking",
                status_code=status.HTTP_409_CONFLICT,
            )

        # ── Mock order create kar ──────────────────────────────────────────
        mock_order_id = None
        now = None
        active_gateway = self._get_active_gateway()
        if active_gateway == PaymentGateway.MOCK:
            mock_order_id = f"mock_order_{uuid.uuid4().hex[:16]}"
            now = datetime.now(timezone.utc)
        else:
            raise RailMindException(
                code="RM-PAY-008",
                message="Razorpay integration not implemented yet",
                status_code=status.HTTP_501_NOT_IMPLEMENTED,
            )

        payment = Payments(
            booking_id=booking.id,
            amount=Decimal(str(booking.total_fare)),
            currency="INR",
            payment_status=PaymentStatus.PENDING,
            gateway=active_gateway,
            gateway_order_id=mock_order_id,
            initiated_at=now,
        )
        if booking.booking_status == BookingStatus.INITIATED:
            booking.booking_status = BookingStatus.PAYMENT_PENDING

        db.add(payment)
        await db.commit()
        await db.refresh(payment)

        return payment, booking

    async def process_payment(
        self,
        request: PaymentProcessRequestDTO,
        current_user: dict,
        db: AsyncSession,
    ) -> tuple[Payments, Bookings]:
        # ── Payment fetch ──────────────────────────────────────────────────
        result = await db.execute(
            select(Payments).where(Payments.id == request.payment_id)
        )
        payment = result.scalar_one_or_none()

        if not payment:
            raise RailMindException(
                code="RM-PAY-006",
                message="Payment not found",
                status_code=status.HTTP_404_NOT_FOUND,
            )

        if payment.payment_status != PaymentStatus.PENDING:
            raise RailMindException(
                code="RM-PAY-004",
                message=f"Payment already processed (status: {payment.payment_status})",
                status_code=status.HTTP_409_CONFLICT,
            )

        # ── Booking fetch + ownership check ────────────────────────────────
        # booking_passengers eager-load — confirm/release dono ko allocation
        # (CNF/RAC/WL) chahiye, aur async me lazy-load fail karega.
        result = await db.execute(
            select(Bookings)
            .options(selectinload(Bookings.booking_passengers))
            .where(Bookings.id == payment.booking_id)
        )
        booking = result.scalar_one_or_none()

        if str(booking.user_id) != str(current_user.get("sub")):
            raise RailMindException(
                code="RM-AUTH-005",
                message="Payment does not belong to current user",
                status_code=status.HTTP_403_FORBIDDEN,
            )

        # ── Credentials validate karo (mock logic) ─────────────────────────
        is_valid, failure_reason = self._validate_mock_credentials(request)
        now = datetime.now(timezone.utc)

        if not is_valid:
            payment.payment_status = PaymentStatus.FAILED
            payment.payment_method = request.payment_method
            payment.failure_reason = failure_reason
            payment.failure_code = "MOCK_INVALID_CREDENTIALS"
            payment.failed_at = now
            payment.gateway_response = {
                "mock": True,
                "reason": failure_reason,
                "method": request.payment_method.value,
            }
            # Payment fail → booking ne jo seat/RAC/WL HOLD kiya tha use release
            # karo (warna held seat hamesha ke liye block reh jaata hai).
            await booking_service.release_booking_after_failed_payment(
                db=db, booking=booking
            )
            await db.commit()
            await db.refresh(payment)
            await db.refresh(booking)
            return payment, booking

        # ── Success path ───────────────────────────────────────────────────
        payment.payment_status = PaymentStatus.SUCCESS
        payment.payment_method = request.payment_method
        payment.paid_at = now
        payment.gateway_payment_id = f"mock_pay_{uuid.uuid4().hex[:16]}"
        payment.gateway_response = {
            "mock": True,
            "method": request.payment_method.value,
            "captured": True,
            # Masked detail (UPI id / card last-4 / netbanking user) — receipt pe
            # "UPI · ananya@oksbi" dikhane ke liye.
            "payment_detail": self._mask_payment_detail(request),
        }

        # Payment success → held booking ko uske final status (confirmed/rac/
        # waitlisted) par promote karo. Inventory pehle hi (booking banते waqt)
        # hold ho chuka hai, isliye sirf status flip hota hai.
        await booking_service.confirm_booking_after_payment(db=db, booking=booking)

        await db.commit()
        await db.refresh(payment)
        await db.refresh(booking)

        task_send_booking_confirmation.delay(str(booking.id))

        return payment, booking

    async def get_payment_status(
        self,
        payment_id: uuid.UUID,
        current_user: dict,
        db: AsyncSession,
    ) -> Payments:
        result = await db.execute(
            select(Payments, Bookings)
            .join(Bookings, Payments.booking_id == Bookings.id)
            .where(Payments.id == payment_id)
        )
        row = result.first()

        if not row:
            raise RailMindException(
                code="RM-PAY-006",
                message="Payment not found",
                status_code=status.HTTP_404_NOT_FOUND,
            )

        payment, booking = row

        if str(booking.user_id) != str(current_user.get("sub")):
            raise RailMindException(
                code="RM-AUTH-005",
                message="Payment does not belong to current user",
                status_code=status.HTTP_403_FORBIDDEN,
            )

        return payment

    # ─── Private — mock credential validation ─────────────────────────────
    @staticmethod
    def _mask_payment_detail(request: PaymentProcessRequestDTO) -> str | None:
        """
        Receipt pe dikhane ke liye masked payment detail:
            UPI        → upi_id (e.g. "ananya@oksbi")
            CARD       → "•••• 4242"
            NETBANKING → username
        Sensitive data (full card / cvv / password) kabhi store nahi hota.
        """
        if request.payment_method == PaymentMethod.UPI:
            return request.upi_id
        if request.payment_method == PaymentMethod.CARD and request.card_number:
            return f"•••• {request.card_number[-4:]}"
        if request.payment_method == PaymentMethod.NETBANKING:
            return request.netbanking_user
        return None

    def _get_active_gateway(self) -> PaymentGateway:
        """Return active payment gateway based on env config."""
        mode = settings.PAYMENT_MODE.lower()
        if mode == "razorpay":
            return PaymentGateway.RAZORPAY
        if mode == "mock":
            return PaymentGateway.MOCK
        raise RailMindException(
            code="RM-PAY-007",
            message=f"Invalid PAYMENT_MODE in config: {settings.PAYMENT_MODE}",
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )

    def _validate_mock_credentials(
        self, request: PaymentProcessRequestDTO
    ) -> tuple[bool, str | None]:
        method = request.payment_method

        if method == PaymentMethod.CARD:
            valid_numbers = {
                settings.MOCK_VALID_CREDIT_CARD,
                settings.MOCK_VALID_DEBIT_CARD,
            }
            if request.card_number not in valid_numbers:
                return False, "Invalid card number"
            if request.card_cvv != settings.MOCK_VALID_CVV:
                return False, "Invalid CVV"
            return True, None

        if method == PaymentMethod.UPI:
            if request.upi_id != settings.MOCK_VALID_UPI_ID:
                return False, "Invalid UPI ID"
            return True, None

        if method == PaymentMethod.NETBANKING:
            if request.netbanking_user != settings.MOCK_VALID_NETBANKING_USER:
                return False, "Invalid netbanking username"
            if request.netbanking_password != settings.MOCK_VALID_NETBANKING_PASS:
                return False, "Invalid netbanking password"
            return True, None

        return False, f"Unsupported payment method: {method.value}"
