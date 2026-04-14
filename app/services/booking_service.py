from __future__ import annotations

import random
import string

from fastapi import status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.constants.train import Quota
from app.core.constants.booking import WaitlistType
from app.core.exceptions import RailMindException
from app.db.models.booking import BookingPassengers, Bookings, RACSlots
from app.db.models.train import SeatInventories, TrainStations, Trains
from app.db.models.waiting_list import WaitlistEntries
from app.schemas.Request.bookingRequestDTO import CreateBookingDTO
from app.schemas.Response.bookingResponseDTO import GetBookingDetailsByIdResponse
from app.services.common_service import CommonService
from app.services.train_service import TrainService
from app.utils.helpers import get_utc_timezone

common_service = CommonService()
train_service = TrainService()


class BookingService:

    # ── Public ────────────────────────────────────────────────────────────────

    async def create_booking(
        self,
        payload: CreateBookingDTO,
        current_user_id,
        db: AsyncSession,
    ) -> dict:

        # Step 1 — Train + journey validate karo
        train_data, from_stop, to_stop = await train_service._validate_journey(
            payload.train_number,
            payload=payload,
            db=db,
        )

        # Step 2 — WL type decide karo
        wl_type = train_service._determine_wl_type(
            is_source=from_stop.is_source,
            is_remote_location=from_stop.station.is_remote_location,
            quota=payload.quota,
        )

        # Step 3 — SeatInventories fetch WITH lock (SELECT FOR UPDATE)
        inventory = await self._fetch_inventory_with_lock(
            db=db,
            train_id=train_data.id,
            journey_date=payload.journey_date,
            train_class=payload.train_class,
            quota=payload.quota,
        )

        # Step 4 — Availability check
        availability = inventory.booking_availability
        if availability == "REGRET":
            raise RailMindException(
                code="RM-BKG-001",
                message="No seats, RAC, or waitlist available for this journey",
                status_code=status.HTTP_409_CONFLICT,
            )

        # Step 5 — Passenger count validate karo
        self._validate_passenger_count(
            passenger_count=len(payload.passengers),
            quota=payload.quota,
        )

        # Step 6 — Fare calculate karo (per passenger)
        fares = await self._calculate_passenger_fares(
            db=db,
            train_data=train_data,
            from_stop=from_stop,
            to_stop=to_stop,
            payload=payload,
        )
        total_fare = sum(f.total_fare for f in fares)

        # Step 7 — PNR generate karo
        pnr_number = await self._generate_unique_pnr(db=db)

        # Step 8 — DB writes (single transaction)
        booking = await self._create_booking_records(
            db=db,
            payload=payload,
            train_data=train_data,
            from_stop=from_stop,
            to_stop=to_stop,
            inventory=inventory,
            availability=availability,
            wl_type=wl_type,
            fares=fares,
            total_fare=total_fare,
            pnr_number=pnr_number,
            current_user_id=current_user_id,
        )

        # Step 9 — Notification Celery task (commented until tasks are ready)
        # task_send_booking_confirmation.delay(str(booking.id))

        return {
            "pnr_number": pnr_number,
            "booking_id": booking.id,
            "booking_status": booking.booking_status,
            "train_number": train_data.train_number,
            "train_name": train_data.train_name,
            "journey_date": payload.journey_date,
            "from_station": payload.from_station,
            "to_station": payload.to_station,
            "train_class": payload.train_class,
            "quota": payload.quota,
            "total_fare": total_fare,
            "availability": availability,
            "wl_type": wl_type if availability == "WL" else None,
            "next_wl_position": (
                inventory.next_wl_position if availability == "WL" else None
            ),
            "passengers": len(payload.passengers),
        }

    async def list_user_bookings(self, current_user_id, db: AsyncSession) -> dict:
        result = await db.execute(
            select(Bookings)
            .options(selectinload(Bookings.user))
            .where(Bookings.user_id == current_user_id)
        )
        user_list = result.scalars().all()

        if user_list is None:
            raise RailMindException(
                code="RM-BKG-001",
                message="No User List Found",
                status_code=status.HTTP_404_NOT_FOUND,
            )

        return [
            {
                "train_id": booking.train_id,
                "user_id": booking.user_id,
                "user_name": booking.user.username,
                "pnr_number": booking.pnr_number,
                "booking_status": booking.booking_status,
                "journey_date": booking.journey_date,
            }
            for booking in user_list
        ]

    async def get_booking_details_by_id(
        self, booking_id, current_user_id, db: AsyncSession
    ) -> dict:
        result = await db.execute(
            select(Bookings)
            .options(
                selectinload(Bookings.train),
                selectinload(Bookings.source_station),
                selectinload(Bookings.destination_station),
            )
            .where(Bookings.id == booking_id)
        )

        booking_data = result.scalar_one_or_none()

        if booking_data is None:
            raise RailMindException(
                code="RM-BKG-001",
                message="No User List Found",
                status_code=status.HTTP_404_NOT_FOUND,
            )

        return GetBookingDetailsByIdResponse(
            pnr_number=booking_data.pnr_number,
            booking_status=booking_data.booking_status,
            journey_date=booking_data.journey_date,
            train_class=booking_data.train_class,
            quota=booking_data.quota,
            total_fare=booking_data.total_fare,
            source_station_name=booking_data.source_station.station_name,
            destination_station_name=booking_data.destination_station.station_name,
        )

    # ── Private helpers ───────────────────────────────────────────────────────

    async def _fetch_inventory_with_lock(
        self,
        db: AsyncSession,
        train_id,
        journey_date,
        train_class: str,
        quota: str,
    ) -> SeatInventories:
        """
        Fetch seat inventory with SELECT FOR UPDATE.
        Locks the row — no other transaction can modify counters
        until this transaction commits or rolls back.
        Critical for preventing double bookings under concurrent load.
        """
        result = await db.execute(
            select(SeatInventories)
            .where(
                SeatInventories.train_id == train_id,
                SeatInventories.journey_date == journey_date,
                SeatInventories.train_class == train_class,
                SeatInventories.quota == quota,
            )
            .with_for_update()
        )
        inventory = result.scalar_one_or_none()

        if not inventory:
            raise RailMindException(
                code="RM-TRN-004",
                message="No availability data found for this journey",
                status_code=status.HTTP_404_NOT_FOUND,
            )

        return inventory

    def _validate_passenger_count(
        self,
        passenger_count: int,
        quota: str,
    ) -> None:
        from app.core.constants.booking import (
            MAX_PASSENGERS_PER_BOOKING,
            MAX_PASSENGERS_PER_TATKAL_BOOKING,
        )

        if quota in (Quota.TATKAL, Quota.PREMIUM_TATKAL):
            if passenger_count > MAX_PASSENGERS_PER_TATKAL_BOOKING:
                raise RailMindException(
                    code="RM-BKG-002",
                    message=f"Maximum {MAX_PASSENGERS_PER_TATKAL_BOOKING} passengers allowed for Tatkal",
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                )

        if passenger_count > MAX_PASSENGERS_PER_BOOKING:
            raise RailMindException(
                code="RM-BKG-002",
                message=f"Maximum {MAX_PASSENGERS_PER_BOOKING} passengers allowed per booking",
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            )

    async def _calculate_passenger_fares(
        self,
        db: AsyncSession,
        train_data,
        from_stop,
        to_stop,
        payload: CreateBookingDTO,
    ) -> list:
        """Calculate fare for each passenger individually."""
        fares = []
        for passenger in payload.passengers:
            breakdown = await common_service.calculate_fare(
                db=db,
                train_type=train_data.train_type,
                train_class=payload.train_class,
                from_stop=from_stop,
                to_stop=to_stop,
                quota=payload.quota,
                include_irctc_charge=True,
            )
            fares.append(breakdown)
        return fares

    async def _generate_unique_pnr(self, db: AsyncSession) -> str:
        """
        Generate a unique 10-digit PNR number.
        Retries up to 5 times on collision (extremely rare).
        """
        for _ in range(5):
            pnr = "".join(random.choices(string.digits, k=10))
            result = await db.execute(
                select(Bookings).where(Bookings.pnr_number == pnr)
            )
            if not result.scalar_one_or_none():
                return pnr

        raise RailMindException(
            code="RM-BKG-005",
            message="Failed to generate unique PNR — please retry",
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )

    async def _create_booking_records(
        self,
        db: AsyncSession,
        payload: CreateBookingDTO,
        train_data,
        from_stop,
        to_stop,
        inventory: SeatInventories,
        availability: str,
        wl_type: str,
        fares: list,
        total_fare: float,
        pnr_number: str,
        current_user_id,
    ) -> Bookings:
        """
        All DB writes in one atomic block.
        Write order:
            1. Bookings row
            2. BookingPassengers rows
            3. SeatInventories counters
            4. WaitlistEntries  (WL bookings only)
            5. RACSlots update  (RAC bookings only)
        """
        now = get_utc_timezone()

        # ── Booking status ────────────────────────────────────────────────────
        booking_status_map = {
            "AVAILABLE": "confirmed",
            "RAC": "rac",
            "WL": "waitlisted",
        }
        booking_status = booking_status_map[availability]

        # ── 1. Bookings ───────────────────────────────────────────────────────
        booking = Bookings(
            user_id=current_user_id,
            train_id=train_data.id,
            pnr_number=pnr_number,
            booking_status=booking_status,
            journey_date=payload.journey_date,
            source_station_id=from_stop.station_id,
            destination_station_id=to_stop.station_id,
            train_class=payload.train_class,
            quota=payload.quota,
            total_fare=total_fare,
            booked_at=now,
        )
        db.add(booking)
        await db.flush()  # booking.id generate karo bina commit ke

        # ── 2. BookingPassengers ──────────────────────────────────────────────
        passenger_status_map = {
            "AVAILABLE": "CNF",
            "RAC": "RAC",
            "WL": "WL",
        }
        passenger_status = passenger_status_map[availability]

        booking_passengers = []
        for passenger, fare in zip(payload.passengers, fares):
            bp = BookingPassengers(
                booking_id=booking.id,
                passenger_id=passenger.passenger_id,
                seat_inventory_id=inventory.id,
                berth_preference=passenger.berth_preference,
                passenger_status=passenger_status,
                fare=fare.total_fare,
            )
            db.add(bp)
            booking_passengers.append(bp)

        await db.flush()  # booking_passenger.id generate karo

        # ── 3. SeatInventories counters ───────────────────────────────────────
        passenger_count = len(payload.passengers)

        if availability == "AVAILABLE":
            inventory.available_confirmed_seats -= passenger_count

        elif availability == "RAC":
            inventory.available_rac_slots -= passenger_count
            # ── 5. RACSlots ───────────────────────────────────────────────────
            await self._assign_rac_slots(
                db=db,
                inventory=inventory,
                booking_passengers=booking_passengers,
            )

        elif availability == "WL":
            # ── 4. WaitlistEntries ────────────────────────────────────────────
            for i, bp in enumerate(booking_passengers):
                wl_position = inventory.wl_count + i + 1
                wl_entry = WaitlistEntries(
                    booking_id=booking.id,
                    booking_passenger_id=bp.id,
                    seat_inventory_id=inventory.id,
                    train_class=payload.train_class,
                    quota=payload.quota,
                    wl_type=wl_type,
                    booking_position=wl_position,
                    current_position=wl_position,
                    source_station_id=from_stop.station_id,
                    destination_station_id=to_stop.station_id,
                )
                db.add(wl_entry)

            inventory.wl_count += passenger_count

        return booking

    async def _assign_rac_slots(
        self,
        db: AsyncSession,
        inventory: SeatInventories,
        booking_passengers: list[BookingPassengers],
    ) -> None:
        """
        RAC passengers ko available slots assign karo.
        Partial slot pehle fill karo, phir fresh slot lo.
        """
        for bp in booking_passengers:
            result = await db.execute(
                select(RACSlots)
                .where(
                    RACSlots.seat_inventory_id == inventory.id,
                    RACSlots.is_full == False,
                )
                .order_by(RACSlots.slot_number)
                .limit(1)
                .with_for_update()
            )
            rac_slot = result.scalar_one_or_none()

            if not rac_slot:
                raise RailMindException(
                    code="RM-BKG-001",
                    message="No RAC slots available",
                    status_code=status.HTTP_409_CONFLICT,
                )

            if rac_slot.passenger_1_booking_passenger_id is None:
                rac_slot.passenger_1_booking_passenger_id = bp.id
            else:
                rac_slot.passenger_2_booking_passenger_id = bp.id
                rac_slot.is_full = True


booking_service = BookingService()
