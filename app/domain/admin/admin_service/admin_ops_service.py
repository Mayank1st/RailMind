import uuid

from fastapi_pagination import Params
from fastapi_pagination.bases import AbstractPage
from fastapi_pagination.ext.sqlalchemy import apaginate
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.exceptions import RailMindException
from app.db.models.booking import BookingPassengers, Bookings
from app.db.models.payment import Payments
from app.db.models.refund import Refunds
from app.db.models.train import Stations
from app.db.models.user import Users
from app.domain.admin.constants.admin_ops import ERR_BOOKING_NOT_FOUND
from app.domain.admin.dto.admin_ops_filter_dto import (
    AdminBookingFilterDTO,
    AdminPaymentFilterDTO,
    AdminRefundFilterDTO,
)
from app.domain.admin.dto.admin_ops_response_dto import (
    AdminBookingDetailResponseDTO,
    AdminBookingSummaryDTO,
    AdminPaymentSummaryDTO,
    AdminRefundSummaryDTO,
    PassengerLineDTO,
    PaymentLineDTO,
    RefundLineDTO,
    StationRefDTO,
)


class AdminOpsService:
    """Read-only oversight over existing Bookings / Payments / Refunds tables.

    Instantiated once at module load in the router; every method takes the
    request-scoped `db` session as a parameter (no per-instance state).
    """

    # ── Bookings & PNR ─────────────────────────────────────────────────────

    async def list_bookings(
        self,
        db: AsyncSession,
        booking_filter: AdminBookingFilterDTO,
        params: Params,
    ) -> AbstractPage:
        query = select(Bookings).options(
            selectinload(Bookings.user),
            selectinload(Bookings.train),
            selectinload(Bookings.source_station),
            selectinload(Bookings.destination_station),
        )
        query = booking_filter.filter(query)
        query = booking_filter.sort(query)
        return await apaginate(
            db,
            query,
            params,
            transformer=lambda rows: [
                self._serialize_booking_summary(booking) for booking in rows
            ],
        )

    async def get_booking_detail(
        self, booking_id: uuid.UUID, db: AsyncSession
    ) -> AdminBookingDetailResponseDTO:
        query = (
            select(Bookings)
            .options(
                selectinload(Bookings.user).selectinload(Users.user_profile),
                selectinload(Bookings.user).selectinload(Users.user_contact),
                selectinload(Bookings.train),
                selectinload(Bookings.source_station),
                selectinload(Bookings.destination_station),
                selectinload(Bookings.booking_passengers).selectinload(
                    BookingPassengers.passenger
                ),
                selectinload(Bookings.payments),
                selectinload(Bookings.refunds),
            )
            .where(Bookings.id == booking_id)
        )
        result = await db.execute(query)
        booking = result.scalar_one_or_none()
        if booking is None:
            raise RailMindException(
                code=ERR_BOOKING_NOT_FOUND,
                message="Booking not found.",
                status_code=404,
            )
        return self._serialize_booking_detail(booking)

    # ── Payments ───────────────────────────────────────────────────────────

    async def list_payments(
        self,
        db: AsyncSession,
        payment_filter: AdminPaymentFilterDTO,
        params: Params,
    ) -> AbstractPage:
        query = select(Payments).options(
            selectinload(Payments.booking).selectinload(Bookings.user),
        )
        query = payment_filter.filter(query)
        query = payment_filter.sort(query)
        return await apaginate(
            db,
            query,
            params,
            transformer=lambda rows: [
                self._serialize_payment_summary(payment) for payment in rows
            ],
        )

    # ── Refunds ────────────────────────────────────────────────────────────

    async def list_refunds(
        self,
        db: AsyncSession,
        refund_filter: AdminRefundFilterDTO,
        params: Params,
    ) -> AbstractPage:
        query = select(Refunds).options(
            selectinload(Refunds.booking),
        )
        query = refund_filter.filter(query)
        query = refund_filter.sort(query)
        return await apaginate(
            db,
            query,
            params,
            transformer=lambda rows: [
                self._serialize_refund_summary(refund) for refund in rows
            ],
        )

    # ── Serializers ────────────────────────────────────────────────────────

    @staticmethod
    def _serialize_station(station: Stations) -> StationRefDTO:
        return StationRefDTO(
            station_id=str(station.id),
            station_code=station.station_code,
            station_name=station.station_name,
            city=station.city,
        )

    def _serialize_booking_summary(self, booking: Bookings) -> AdminBookingSummaryDTO:
        return AdminBookingSummaryDTO(
            booking_id=str(booking.id),
            pnr_number=booking.pnr_number,
            booking_status=booking.booking_status,
            journey_date=booking.journey_date,
            train_class=booking.train_class,
            quota=booking.quota,
            total_fare=booking.total_fare,
            booked_at=booking.booked_at,
            train_number=booking.train.train_number if booking.train else None,
            train_name=booking.train.train_name if booking.train else None,
            source_station=self._serialize_station(booking.source_station),
            destination_station=self._serialize_station(booking.destination_station),
            user_id=str(booking.user_id),
            user_name=booking.user.username if booking.user else None,
            user_email=booking.user.email if booking.user else None,
        )

    def _serialize_booking_detail(
        self, booking: Bookings
    ) -> AdminBookingDetailResponseDTO:
        user = booking.user
        contact = user.user_contact if user else None
        return AdminBookingDetailResponseDTO(
            booking_id=str(booking.id),
            pnr_number=booking.pnr_number,
            booking_status=booking.booking_status,
            journey_date=booking.journey_date,
            train_class=booking.train_class,
            quota=booking.quota,
            total_fare=booking.total_fare,
            booked_at=booking.booked_at,
            created_at=booking.created_at,
            train_id=str(booking.train_id),
            train_number=booking.train.train_number if booking.train else None,
            train_name=booking.train.train_name if booking.train else None,
            source_station=self._serialize_station(booking.source_station),
            destination_station=self._serialize_station(booking.destination_station),
            user_id=str(booking.user_id),
            user_name=user.username if user else None,
            user_email=user.email if user else None,
            user_mobile=contact.mobile_number if contact else None,
            passengers=[
                self._serialize_passenger(bp) for bp in booking.booking_passengers
            ],
            payments=[
                self._serialize_payment_line(payment) for payment in booking.payments
            ],
            refunds=[self._serialize_refund_line(refund) for refund in booking.refunds],
        )

    @staticmethod
    def _serialize_passenger(bp: BookingPassengers) -> PassengerLineDTO:
        passenger = bp.passenger
        return PassengerLineDTO(
            passenger_id=str(bp.passenger_id),
            full_name=passenger.full_name if passenger else None,
            age=passenger.age if passenger else None,
            gender=passenger.gender if passenger else None,
            berth_preference=bp.berth_preference,
            allotted_berth=bp.allotted_berth,
            passenger_status=bp.passenger_status,
            fare=bp.fare,
        )

    @staticmethod
    def _serialize_payment_line(payment: Payments) -> PaymentLineDTO:
        return PaymentLineDTO(
            payment_id=str(payment.id),
            amount=float(payment.amount),
            currency=payment.currency,
            payment_method=(
                payment.payment_method.value if payment.payment_method else None
            ),
            payment_status=payment.payment_status.value,
            gateway=payment.gateway.value,
            gateway_order_id=payment.gateway_order_id,
            gateway_payment_id=payment.gateway_payment_id,
            failure_reason=payment.failure_reason,
            failure_code=payment.failure_code,
            initiated_at=payment.initiated_at,
            paid_at=payment.paid_at,
            failed_at=payment.failed_at,
        )

    def _serialize_payment_summary(self, payment: Payments) -> AdminPaymentSummaryDTO:
        booking = payment.booking
        user = booking.user if booking else None
        return AdminPaymentSummaryDTO(
            payment_id=str(payment.id),
            booking_id=str(payment.booking_id),
            pnr_number=booking.pnr_number if booking else None,
            user_email=user.email if user else None,
            amount=float(payment.amount),
            currency=payment.currency,
            payment_method=(
                payment.payment_method.value if payment.payment_method else None
            ),
            payment_status=payment.payment_status.value,
            gateway=payment.gateway.value,
            gateway_order_id=payment.gateway_order_id,
            gateway_payment_id=payment.gateway_payment_id,
            failure_reason=payment.failure_reason,
            failure_code=payment.failure_code,
            initiated_at=payment.initiated_at,
            paid_at=payment.paid_at,
            failed_at=payment.failed_at,
        )

    @staticmethod
    def _serialize_refund_line(refund: Refunds) -> RefundLineDTO:
        return RefundLineDTO(
            refund_id=str(refund.id),
            payment_id=str(refund.payment_id),
            refund_amount=float(refund.refund_amount),
            deduction_amount=float(refund.deduction_amount),
            original_amount=float(refund.original_amount),
            currency=refund.currency,
            refund_status=refund.refund_status.value,
            refund_reason=refund.refund_reason.value,
            refund_notes=refund.refund_notes,
            gateway_refund_id=refund.gateway_refund_id,
            failure_reason=refund.failure_reason,
            initiated_at=refund.initiated_at,
            processed_at=refund.processed_at,
            failed_at=refund.failed_at,
        )

    def _serialize_refund_summary(self, refund: Refunds) -> AdminRefundSummaryDTO:
        booking = refund.booking
        return AdminRefundSummaryDTO(
            refund_id=str(refund.id),
            payment_id=str(refund.payment_id),
            booking_id=str(refund.booking_id),
            pnr_number=booking.pnr_number if booking else None,
            refund_amount=float(refund.refund_amount),
            deduction_amount=float(refund.deduction_amount),
            original_amount=float(refund.original_amount),
            currency=refund.currency,
            refund_status=refund.refund_status.value,
            refund_reason=refund.refund_reason.value,
            gateway_refund_id=refund.gateway_refund_id,
            failure_reason=refund.failure_reason,
            initiated_at=refund.initiated_at,
            processed_at=refund.processed_at,
            failed_at=refund.failed_at,
        )
