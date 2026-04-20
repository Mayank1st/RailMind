from __future__ import annotations

import os
import random
import string
import tempfile

from fastapi import status
from pathlib import Path
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.constants.train import Quota
from app.core.constants.booking import PassengerStatus, BookingStatus
from app.core.exceptions import RailMindException
from app.db.models.booking import BookingPassengers, Bookings, RACSlots
from app.db.models.train import SeatInventories
from app.db.models.passengers import Passengers
from app.db.models.waiting_list import WaitlistEntries
from app.db.models.train import Seats, Coaches, TrainStations
from app.db.models.user import Users
from app.schemas.Request.bookingRequestDTO import CreateBookingDTO
from app.schemas.Response.bookingResponseDTO import GetBookingDetailsByIdResponse
from app.services.common_service import CommonService
from app.services.train_service import TrainService
from app.services.passenger_service import PassengerService
from app.services.ticket_pdf import build_ticket_pdf
from app.utils.helpers import get_utc_timezone

common_service = CommonService()
train_service = TrainService()
passenger_service = PassengerService()


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

        # Step 5.1 - Check Passenger data from DB
        passenger_ids = [p.passenger_id for p in payload.passengers]

        result = await db.execute(
            select(Passengers).where(
                Passengers.id.in_(passenger_ids),
                Passengers.user_id == current_user_id,
                Passengers.is_active == True,
            )
        )
        passengers = result.scalars().all()
        passengers_list = [p.to_dict() for p in passengers]

        if len(passengers_list) != len(payload.passengers):
            raise RailMindException(
                code="RM-BKG-001",
                message=f"Passengers Not Found, Please Create",
                status_code=status.HTTP_404_NOT_FOUND,
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
        booking, booking_passengers = await self._create_booking_records(
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
            "passengers": [
                {
                    "passenger_id": str(bp.passenger_id),
                    "passenger_status": bp.passenger_status,
                    "berth_preference": bp.berth_preference,
                    "allotted_berth": bp.allotted_berth,
                    "seat_id": str(bp.seat_id) if bp.seat_id else None,
                    "seat_number": bp.seat.seat_number,
                    "fare": bp.fare,
                }
                for bp in booking_passengers
            ],
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

    async def cancel_booking(
        self,
        booking_id,
        current_user_id,
        db: AsyncSession,
    ) -> dict:

        # ── 1. Booking fetch + validate ───────────────────────────────────────────
        result = await db.execute(
            select(Bookings)
            .options(selectinload(Bookings.booking_passengers))
            .where(
                Bookings.id == booking_id,
                Bookings.user_id == current_user_id,
            )
        )
        booking = result.scalar_one_or_none()

        if not booking:
            raise RailMindException(
                code="RM-BKG-003",
                message="Booking not found",
                status_code=status.HTTP_404_NOT_FOUND,
            )

        if booking.booking_status == BookingStatus.CANCELLED:
            raise RailMindException(
                code="RM-BKG-004",
                message="Booking is already cancelled",
                status_code=status.HTTP_409_CONFLICT,
            )

        # ── 2. Inventory fetch WITH lock ──────────────────────────────────────────
        inventory = await self._fetch_inventory_with_lock(
            db=db,
            train_id=booking.train_id,
            journey_date=booking.journey_date,
            train_class=booking.train_class,
            quota=booking.quota,
        )

        if inventory.is_chart_prepared:
            raise RailMindException(
                code="RM-BKG-005",
                message="Cannot cancel after chart preparation",
                status_code=status.HTTP_403_FORBIDDEN,
            )

        booking_status = booking.booking_status  # "confirmed" / "rac" / "waitlisted"
        passenger_count = len(booking.booking_passengers)

        # ── 3. BookingPassengers → CAN ────────────────────────────────────────────
        for bp in booking.booking_passengers:
            bp.passenger_status = PassengerStatus.CANCELLED
            bp.seat_id = None  # seat free karo
            bp.allotted_berth = None

        # ── 4. Bookings → cancelled ───────────────────────────────────────────────
        booking.booking_status = BookingStatus.CANCELLED

        # ── 5. SeatInventories counters + cascade ─────────────────────────────────
        if booking_status == BookingStatus.CONFIRMED:
            inventory.available_confirmed_seats += passenger_count
            # Promotion cascade — RAC → CNF, WL → RAC
            await self._run_promotion_cascade(
                db=db,
                inventory=inventory,
                freed_count=passenger_count,
            )

        elif booking_status == BookingStatus.RAC:
            inventory.available_rac_slots += passenger_count
            # RACSlots clean up — ondelete SET NULL handles passenger FKs
            # is_full = False karo
            await self._clear_rac_slots(
                db=db,
                inventory=inventory,
                booking_passengers=booking.booking_passengers,
            )
            # WL → RAC promote karo
            await self._promote_wl_to_rac(
                db=db,
                inventory=inventory,
                count=passenger_count,
            )

        elif booking_status == BookingStatus.WAITLISTED:
            # WaitlistEntries cancel karo
            wl_result = await db.execute(
                select(WaitlistEntries).where(
                    WaitlistEntries.booking_id == booking.id,
                    WaitlistEntries.is_promoted == False,
                    WaitlistEntries.is_auto_cancelled == False,
                )
            )
            wl_entries = wl_result.scalars().all()

            for wl_entry in wl_entries:
                wl_entry.is_auto_cancelled = True
                wl_entry.auto_cancelled_at = get_utc_timezone()

            inventory.wl_count -= len(wl_entries)

            # Baaki WL positions decrement karo
            await self._decrement_wl_positions(
                db=db,
                inventory=inventory,
                cancelled_positions=[wl.booking_position for wl in wl_entries],
            )

        await db.flush()

        return {
            "booking_id": str(booking.id),
            "pnr_number": booking.pnr_number,
            "booking_status": booking.booking_status,
        }

    async def download_receipt(
        self,
        booking_id: str,
        current_user_id,
        db: AsyncSession,
    ) -> dict:

        result = await db.execute(
            select(Bookings)
            .options(
                selectinload(Bookings.train),
                selectinload(Bookings.source_station),
                selectinload(Bookings.destination_station),
                selectinload(Bookings.user).selectinload(Users.user_contact),
                selectinload(Bookings.user).selectinload(Users.user_profile),
                selectinload(Bookings.booking_passengers).selectinload(
                    BookingPassengers.passenger
                ),
                # seat → coach
                selectinload(Bookings.booking_passengers)
                .selectinload(BookingPassengers.seat)
                .selectinload(Seats.coach),
                # seat_inventory — completely alag chain
                selectinload(Bookings.booking_passengers).selectinload(
                    BookingPassengers.seat_inventory
                ),
            )
            .where(Bookings.id == booking_id)
        )
        booking = result.scalar_one_or_none()

        if not booking:
            raise RailMindException(
                code="RM-BKG-003",
                message="Booking not found",
                status_code=status.HTTP_404_NOT_FOUND,
            )

        # ── Train stops fetch karo — departure/arrival time ke liye ──────────────
        stops_result = await db.execute(
            select(TrainStations)
            .options(selectinload(TrainStations.station))
            .where(TrainStations.train_id == booking.train_id)
            .order_by(TrainStations.sequence_number)
        )
        stops = stops_result.scalars().all()

        # Source aur destination stop dhundho
        from_stop = next(
            (s for s in stops if s.station_id == booking.source_station_id), None
        )
        to_stop = next(
            (s for s in stops if s.station_id == booking.destination_station_id), None
        )

        # ── Distance aur duration calculate karo ─────────────────────────────────
        distance_km = 0
        if from_stop and to_stop:
            distance_km = to_stop.distance_km - from_stop.distance_km

        inventory = (
            booking.booking_passengers[0].seat_inventory
            if booking.booking_passengers
            else None
        )

        # ── Ticket dict banao ─────────────────────────────────────────────────────
        ticket_payload = {
            "pnr_number": booking.pnr_number,
            "booking_status": booking.booking_status.upper(),
            "booked_at": booking.booked_at.strftime("%d %b %Y, %I:%M %p"),
            "journey_date": booking.journey_date.strftime("%d %b %Y"),
            "journey_day": booking.journey_date.strftime("%A"),
            "train_number": booking.train.train_number,
            "train_name": booking.train.train_name,
            "train_type": booking.train.train_type,
            "train_class": booking.train_class,
            "quota": booking.quota,
            "source_station": booking.source_station.station_code,
            "source_name": booking.source_station.station_name,
            "departure_time": str(from_stop.departure_time)[:5] if from_stop else "—",
            "dest_station": booking.destination_station.station_code,
            "dest_name": booking.destination_station.station_name,
            "arrival_time": str(to_stop.arrival_time)[:5] if to_stop else "—",
            "arrival_day": None,  # multi-day journey logic baad mein
            "distance_km": f"{distance_km:,}",
            "duration": "—",  # calculate from departure/arrival if needed
            "coach": (
                booking.booking_passengers[0].seat.coach.coach_number
                if booking.booking_passengers and booking.booking_passengers[0].seat
                else "—"
            ),
            "boarding_station": f"{booking.source_station.station_code} - {booking.source_station.station_name}",
            "chart_status": (
                "CHART PREPARED"
                if inventory and inventory.is_chart_prepared
                else "CHART NOT PREPARED"
            ),
            "passengers": [
                {
                    "name": bp.passenger.full_name.upper(),
                    "age": bp.passenger.age,
                    "gender": bp.passenger.gender,
                    "seat": (
                        f"{bp.seat.seat_number} / {bp.allotted_berth}"
                        if bp.seat and bp.allotted_berth
                        else "—"
                    ),
                    "status": bp.passenger_status,
                    "fare": bp.fare,
                    "id_type": bp.passenger.id_type or "—",
                    "id_number": bp.passenger.id_number or "—",
                }
                for bp in booking.booking_passengers
            ],
            "fare_breakdown": {
                "base_fare": booking.total_fare,
                "reservation_charge": 0.0,
                "superfast_charge": 0.0,
                "gst": 0.0,
                "insurance": 0.0,
                "total_fare": booking.total_fare,
            },
            "payment": {
                "txn_id": "—",
                "method": "—",
                "status": "—",
            },
            "user": {
                "name": booking.user.username,
                "email": (
                    booking.user.user_profile.first_name
                    + " "
                    + booking.user.user_profile.last_name
                    if booking.user.user_profile
                    else booking.user.username
                ),
                "phone": (
                    booking.user.user_contact.mobile_number
                    if booking.user.user_contact
                    else "—"
                ),
            },
        }

        PROJECT_ROOT = Path(__file__).resolve().parent.parent
        RECEIPTS_DIR = PROJECT_ROOT / "receipts"
        RECEIPTS_DIR.mkdir(exist_ok=True)

        # with tempfile.NamedTemporaryFile(
        #     suffix=".pdf", prefix=f"ticket_{booking.pnr_number}_", delete=False
        # ) as tmp:
        #     output_path = tmp.name

        output_path = str(RECEIPTS_DIR / f"ticket_{booking.pnr_number}.pdf")

        build_ticket_pdf(ticket=ticket_payload, output_path=output_path)
        return output_path

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
    ) -> tuple[Bookings, list[BookingPassengers]]:
        """
        All DB writes in one atomic block.
        Write order:
            1. Bookings row
            2. Seat allocation (CNF only)
            3. BookingPassengers rows
            4. SeatInventories counters
            5. WaitlistEntries  (WL bookings only)
            6. RACSlots update  (RAC bookings only)
        """
        now = get_utc_timezone()

        # ── Booking status ────────────────────────────────────────────────────────
        booking_status_map = {
            "AVAILABLE": "confirmed",
            "RAC": "rac",
            "WL": "waitlisted",
        }
        booking_status = booking_status_map[availability]

        # ── 1. Bookings ───────────────────────────────────────────────────────────
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
        await db.flush()

        # ── 2. Seat allocation (CNF only) ─────────────────────────────────────────
        # RAC → side-lower shared berth (handled in _assign_rac_slots)
        # WL  → no seat until chart preparation
        assigned_seats = []
        if availability == "AVAILABLE":
            assigned_seats = await self._allocate_seats(
                db=db,
                train_id=train_data.id,
                journey_date=payload.journey_date,
                train_class=payload.train_class,
                passengers=payload.passengers,
            )

        # ── 3. BookingPassengers ──────────────────────────────────────────────────
        passenger_status_map = {
            "AVAILABLE": "CNF",
            "RAC": "RAC",
            "WL": "WL",
        }
        passenger_status = passenger_status_map[availability]

        booking_passengers = []
        for i, (passenger, fare) in enumerate(zip(payload.passengers, fares)):
            seat = assigned_seats[i] if assigned_seats else None

            bp = BookingPassengers(
                booking_id=booking.id,
                passenger_id=passenger.passenger_id,
                seat_inventory_id=inventory.id,
                berth_preference=passenger.berth_preference,
                passenger_status=passenger_status,
                fare=fare.total_fare,
                seat_id=seat.Seats.id if seat else None,
                allotted_berth=seat.Seats.berth_type if seat else None,
            )
            db.add(bp)
            booking_passengers.append(bp)

        await db.flush()

        # ── 4. SeatInventories counters ───────────────────────────────────────────
        passenger_count = len(payload.passengers)

        if availability == "AVAILABLE":
            inventory.available_confirmed_seats -= passenger_count

        elif availability == "RAC":
            inventory.available_rac_slots -= passenger_count
            await self._assign_rac_slots(
                db=db,
                inventory=inventory,
                booking_passengers=booking_passengers,
            )

        elif availability == "WL":
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

        return booking, booking_passengers

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

    async def _allocate_seats(
        self,
        db: AsyncSession,
        train_id,
        journey_date,
        train_class: str,
        passengers: list,
    ) -> list:

        # Already booked seat IDs fetch karo
        booked_result = await db.execute(
            select(BookingPassengers.seat_id)
            .join(Bookings, Bookings.id == BookingPassengers.booking_id)
            .where(
                Bookings.train_id == train_id,
                Bookings.journey_date == journey_date,
                Bookings.train_class == train_class,
                BookingPassengers.seat_id.is_not(None),
                BookingPassengers.passenger_status != PassengerStatus.CANCELLED,
            )
        )
        booked_seat_ids = {row.seat_id for row in booked_result.fetchall()}

        # Is train ke available seats fetch karo
        seats_result = await db.execute(
            select(Seats, Coaches.coach_number)
            .join(Coaches, Coaches.id == Seats.coach_id)
            .where(
                Coaches.train_id == train_id,
                Coaches.train_class == train_class,
                Seats.is_rac_berth == False,
                Seats.id.not_in(booked_seat_ids) if booked_seat_ids else True,
            )
            .order_by(Coaches.coach_position, Seats.seat_number)
        )
        available_seats = seats_result.fetchall()

        # Har passenger ke liye seat assign karo
        assigned_seats = []
        used_seat_ids = set()

        for passenger in passengers:
            preference = passenger.berth_preference

            # Exact match try karo
            seat = next(
                (
                    row
                    for row in available_seats
                    if row.Seats.berth_type == preference
                    and row.Seats.id not in used_seat_ids
                ),
                None,
            )

            # Koi bhi available seat lo
            if not seat:
                seat = next(
                    (
                        row
                        for row in available_seats
                        if row.Seats.id not in used_seat_ids
                    ),
                    None,
                )

            if not seat:
                raise RailMindException(
                    code="RM-BKG-001",
                    message="No seats available to assign",
                    status_code=status.HTTP_409_CONFLICT,
                )

            used_seat_ids.add(seat.Seats.id)
            assigned_seats.append(seat)

        return assigned_seats

    async def _run_promotion_cascade(
        self,
        db: AsyncSession,
        inventory: SeatInventories,
        freed_count: int,
    ) -> None:
        """CNF cancel → RAC promote → WL promote."""
        for _ in range(freed_count):
            # RAC/1 → CNF
            rac_result = await db.execute(
                select(RACSlots)
                .where(
                    RACSlots.seat_inventory_id == inventory.id,
                    RACSlots.passenger_1_booking_passenger_id.is_not(None),
                )
                .order_by(RACSlots.slot_number)
                .limit(1)
                .with_for_update()
            )
            rac_slot = rac_result.scalar_one_or_none()

            if rac_slot:
                # RAC passenger promote to CNF
                bp_result = await db.execute(
                    select(BookingPassengers).where(
                        BookingPassengers.id
                        == rac_slot.passenger_1_booking_passenger_id
                    )
                )
                rac_bp = bp_result.scalar_one_or_none()
                if rac_bp:
                    rac_bp.passenger_status = "CNF"
                    rac_slot.passenger_1_booking_passenger_id = (
                        rac_slot.passenger_2_booking_passenger_id
                    )
                    rac_slot.passenger_2_booking_passenger_id = None
                    rac_slot.is_full = False
                    inventory.available_rac_slots += 1

                    # WL/1 → RAC
                    await self._promote_wl_to_rac(db=db, inventory=inventory, count=1)

    async def _promote_wl_to_rac(
        self,
        db: AsyncSession,
        inventory: SeatInventories,
        count: int,
    ) -> None:
        """WL mein se next promotable passenger ko RAC mein upgrade karo."""
        for _ in range(count):
            if inventory.available_rac_slots <= 0:
                break

            # Priority: GNWL > RLWL > PQWL
            wl_result = await db.execute(
                select(WaitlistEntries)
                .where(
                    WaitlistEntries.seat_inventory_id == inventory.id,
                    WaitlistEntries.is_promoted == False,
                    WaitlistEntries.is_auto_cancelled == False,
                    WaitlistEntries.wl_type.in_(["GNWL", "RLWL", "PQWL"]),
                )
                .order_by(
                    WaitlistEntries.wl_type,  # GNWL first
                    WaitlistEntries.current_position,
                )
                .limit(1)
                .with_for_update()
            )
            wl_entry = wl_result.scalar_one_or_none()

            if not wl_entry:
                break

            # WL → RAC
            wl_entry.is_promoted = True
            wl_entry.promoted_to = "RAC"
            wl_entry.promoted_at = get_utc_timezone()

            # BookingPassengers status update
            bp_result = await db.execute(
                select(BookingPassengers).where(
                    BookingPassengers.id == wl_entry.booking_passenger_id
                )
            )
            wl_bp = bp_result.scalar_one_or_none()
            if wl_bp:
                wl_bp.passenger_status = "RAC"

            inventory.available_rac_slots -= 1
            inventory.wl_count -= 1

    async def _clear_rac_slots(
        self,
        db: AsyncSession,
        inventory: SeatInventories,
        booking_passengers,
    ) -> None:
        """RAC cancel hone pe slots clear karo."""
        for bp in booking_passengers:
            result = await db.execute(
                select(RACSlots).where(
                    RACSlots.seat_inventory_id == inventory.id,
                    RACSlots.passenger_1_booking_passenger_id == bp.id,
                )
            )
            slot = result.scalar_one_or_none()

            if slot:
                slot.passenger_1_booking_passenger_id = (
                    slot.passenger_2_booking_passenger_id
                )
                slot.passenger_2_booking_passenger_id = None
                slot.is_full = False

    async def _decrement_wl_positions(
        self,
        db: AsyncSession,
        inventory: SeatInventories,
        cancelled_positions: list[int],
    ) -> None:
        """
        Cancelled WL positions se aage wale sabhi passengers ki
        current_position -= 1 karo.
        """
        if not cancelled_positions:
            return

        min_position = min(cancelled_positions)

        result = await db.execute(
            select(WaitlistEntries).where(
                WaitlistEntries.seat_inventory_id == inventory.id,
                WaitlistEntries.is_promoted == False,
                WaitlistEntries.is_auto_cancelled == False,
                WaitlistEntries.current_position > min_position,
            )
        )
        remaining_wl = result.scalars().all()

        for wl in remaining_wl:
            wl.current_position -= len(
                [p for p in cancelled_positions if p < wl.current_position]
            )


booking_service = BookingService()
