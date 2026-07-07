from fastapi import status

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.db.models import Bookings, BookingPassengers
from app.db.models.train import Seats
from app.core.exceptions import RailMindException


class PnrService:
    async def get_pnr_status_of_current_user(
        self, pnr_number: str, current_user_id, db: AsyncSession
    ) -> dict:
        result = await db.execute(
            select(Bookings)
            .options(
                selectinload(Bookings.train),
                selectinload(Bookings.source_station),
                selectinload(Bookings.destination_station),
                selectinload(Bookings.booking_passengers).selectinload(
                    BookingPassengers.passenger
                ),
                selectinload(Bookings.booking_passengers)
                .selectinload(BookingPassengers.seat)
                .selectinload(Seats.coach),
            )
            .where(
                Bookings.pnr_number == pnr_number,
                Bookings.user_id == current_user_id,
            )
        )

        booking = result.scalar_one_or_none()

        if not booking:
            raise RailMindException(
                code="RM-PNR-001",
                message="PNR not found",
                status_code=status.HTTP_404_NOT_FOUND,
            )

        return {
            "pnr_number": booking.pnr_number,
            "booking_status": booking.booking_status,
            "booked_at": booking.booked_at,
            "journey_date": booking.journey_date,
            "train_class": booking.train_class,
            "quota": booking.quota,
            "total_fare": booking.total_fare,
            "train_number": booking.train.train_number,
            "train_name": booking.train.train_name,
            "train_type": booking.train.train_type,
            "source_station_code": booking.source_station.station_code,
            "source_station_name": booking.source_station.station_name,
            "destination_station_code": booking.destination_station.station_code,
            "destination_station_name": booking.destination_station.station_name,
            "passengers": [
                {
                    "passenger_status": bp.passenger_status,
                    "allotted_berth": bp.allotted_berth,
                    "fare": bp.fare,
                    "seat_number": bp.seat.seat_number if bp.seat else None,
                    "berth_type": bp.seat.berth_type if bp.seat else None,
                    "coach_number": (
                        bp.seat.coach.coach_number
                        if bp.seat and bp.seat.coach
                        else None
                    ),
                }
                for bp in booking.booking_passengers
            ],
        }

    async def get_pnr_status(self, pnr_number: str, db: AsyncSession) -> dict:
        result = await db.execute(
            select(Bookings)
            .options(
                selectinload(Bookings.train),
                selectinload(Bookings.source_station),
                selectinload(Bookings.destination_station),
                selectinload(Bookings.booking_passengers).selectinload(
                    BookingPassengers.passenger
                ),
                selectinload(Bookings.booking_passengers)
                .selectinload(BookingPassengers.seat)
                .selectinload(Seats.coach),
                selectinload(Bookings.booking_passengers).selectinload(
                    BookingPassengers.waitlist_entry
                ),
            )
            .where(Bookings.pnr_number == pnr_number)
        )
        booking = result.scalar_one_or_none()

        if not booking:
            raise RailMindException(
                code="RM-PNR-001",
                message="PNR not found",
                status_code=status.HTTP_404_NOT_FOUND,
            )

        first_wl = next(
            (
                bp.waitlist_entry
                for bp in booking.booking_passengers
                if bp.waitlist_entry
            ),
            None,
        )

        return {
            "pnr_number": booking.pnr_number,
            "booking_status": booking.booking_status,
            "booked_at": booking.booked_at,
            "journey_date": booking.journey_date,
            "train_class": booking.train_class,
            "quota": booking.quota,
            "total_fare": booking.total_fare,
            "wl_type": first_wl.wl_type if first_wl else None,
            "wl_position": first_wl.current_position if first_wl else None,
            "train_number": booking.train.train_number,
            "train_name": booking.train.train_name,
            "train_type": booking.train.train_type,
            "source_station_code": booking.source_station.station_code,
            "source_station_name": booking.source_station.station_name,
            "destination_station_code": booking.destination_station.station_code,
            "destination_station_name": booking.destination_station.station_name,
            "passengers": [
                {
                    "passenger_name": bp.passenger.full_name.upper(),
                    "passenger_age": bp.passenger.age,
                    "passenger_gender": bp.passenger.gender,
                    "passenger_status": bp.passenger_status,
                    "allotted_berth": bp.allotted_berth,
                    "fare": bp.fare,
                    "seat_number": bp.seat.seat_number if bp.seat else None,
                    "berth_type": bp.seat.berth_type if bp.seat else None,
                    "coach_number": (
                        bp.seat.coach.coach_number
                        if bp.seat and bp.seat.coach
                        else None
                    ),
                }
                for bp in booking.booking_passengers
            ],
        }
