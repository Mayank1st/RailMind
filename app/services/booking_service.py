from __future__ import annotations

import random
import string

from fastapi import status
from sqlalchemy import Select, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from datetime import date
import logging
import threading
import asyncio

from app.core.constants.train import Quota
from app.core.constants.booking import (
    PassengerStatus,
    BookingStatus,
    JourneyActionType,
    BookingJourneyFilter,
    CANCELLED_BOOKING_STATUSES,
)
from fastapi_pagination import Params
from fastapi_pagination.ext.sqlalchemy import apaginate
from app.core.constants.payment import PaymentStatus
from app.core.exceptions import RailMindException
from app.db.models.booking import BookingPassengers, Bookings, RACSlots
from app.db.models.train import SeatInventories, Trains
from app.db.models.passengers import Passengers
from app.db.models.waiting_list import WaitlistEntries
from app.db.models.train import Seats, Coaches, TrainStations
from app.db.models.user import Users
from app.schemas.Request.bookingRequestDTO import CreateBookingDTO, FarePreviewDTO
from app.schemas.Response.bookingResponseDTO import GetBookingDetailsByIdResponse
from app.services.common_service import CommonService
from app.services.train_service import TrainService
from app.services.passenger_service import PassengerService
from app.services.ticket_pdf import build_ticket_pdf
from app.utils.helpers import get_utc_timezone
from app.integrations.supabase_client import upload_pdf_to_supabase

common_service = CommonService()
train_service = TrainService()
passenger_service = PassengerService()

logger = logging.getLogger(__name__)

# ── Receipt display labels — raw class/quota codes ko human-readable banane ke liye ──
TRAIN_CLASS_LABELS = {
    "SL": "Sleeper (SL)",
    "3A": "AC 3-Tier (3A)",
    "2A": "AC 2-Tier (2A)",
    "1A": "AC First Class (1A)",
    "CC": "Chair Car (CC)",
    "2S": "Second Sitting (2S)",
    "FC": "First Class (FC)",
    "3E": "AC 3-Tier Economy (3E)",
}

QUOTA_LABELS = {
    "GN": "General (GN)",
    "TQ": "Tatkal (TQ)",
    "PT": "Premium Tatkal (PT)",
    "LD": "Ladies (LD)",
    "LB": "Lower Berth (LB)",
    "HP": "Handicapped (HP)",
    "DF": "Defence (DF)",
    "SS": "Senior Citizen (SS)",
    "FT": "Foreign Tourist (FT)",
}

# ── Tax-invoice seller details ──────────────────────────────────────────────────
# NOTE: ideally settings/config se aaye; abhi ticket_pdf ke saath consistent constant.
RECEIPT_SELLER_INFO = {
    "name": "RailMind Technologies Pvt. Ltd.",
    "website": "railmind.app",
    "email": "help@railmind.app",
    "gstin": "27AABCR1234M1Z5",
}


class BookingService:

    # ── Public ────────────────────────────────────────────────────────────────

    async def create_booking(
        self,
        payload: CreateBookingDTO,
        current_user_id,
        db: AsyncSession,
    ) -> dict:

        logger.info(
            "create_booking called; thread=%s; loop=%s",
            threading.current_thread().name,
            asyncio.get_running_loop(),
        )

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
        booking, booking_passengers, seat_numbers = await self._create_booking_records(
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
                    "seat_number": seat_numbers[idx],
                    "fare": bp.fare,
                }
                for idx, bp in enumerate(booking_passengers)
            ],
        }

    def _user_bookings_base_stmt(self, current_user_id):
        """Base SELECT for a user's bookings with summary relationships eager-loaded."""
        return (
            select(Bookings)
            .options(
                selectinload(Bookings.user),
                selectinload(Bookings.train),
                selectinload(Bookings.source_station),
                selectinload(Bookings.destination_station),
            )
            .where(Bookings.user_id == current_user_id)
        )

    @staticmethod
    def _serialize_booking_summary(booking) -> dict:
        return {
            "booking_id": booking.id,
            "train_id": booking.train_id,
            "train_number": booking.train.train_number,
            "train_name": booking.train.train_name,
            "source_station": booking.source_station.station_code,
            "destination_station": booking.destination_station.station_code,
            "user_id": booking.user_id,
            "user_name": booking.user.username,
            "pnr_number": booking.pnr_number,
            "booking_status": booking.booking_status,
            "journey_date": booking.journey_date,
        }

    async def get_all_user_bookings(
        self, current_user_id, db: AsyncSession
    ) -> list[dict]:
        result = await db.execute(self._user_bookings_base_stmt(current_user_id))
        return [self._serialize_booking_summary(b) for b in result.scalars().all()]

    async def list_user_bookings(
        self,
        current_user_id,
        db: AsyncSession,
        *,
        journey_filter: BookingJourneyFilter = BookingJourneyFilter.ALL,
        params: Params,
    ):
        today = date.today()
        stmt = self._user_bookings_base_stmt(current_user_id)

        if journey_filter == BookingJourneyFilter.UPCOMING:
            stmt = stmt.where(
                Bookings.journey_date >= today,
                Bookings.booking_status.notin_(CANCELLED_BOOKING_STATUSES),
            ).order_by(Bookings.journey_date.asc())
        elif journey_filter == BookingJourneyFilter.COMPLETED:
            stmt = stmt.where(
                Bookings.journey_date < today,
                Bookings.booking_status.notin_(CANCELLED_BOOKING_STATUSES),
            ).order_by(Bookings.journey_date.desc())
        elif journey_filter == BookingJourneyFilter.CANCELLED:
            stmt = stmt.where(
                Bookings.booking_status.in_(CANCELLED_BOOKING_STATUSES),
            ).order_by(Bookings.journey_date.desc())
        else:  # BookingJourneyFilter.ALL
            stmt = stmt.order_by(Bookings.journey_date.desc())

        return await apaginate(
            db,
            stmt,
            params,
            transformer=lambda rows: [self._serialize_booking_summary(b) for b in rows],
        )

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
            source_station_code=booking_data.source_station.station_code,
            destination_station_name=booking_data.destination_station.station_name,
            destination_station_code=booking_data.destination_station.station_code,
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

        # ── 3-5. Held inventory release karo (counters + RAC/WL cascade) ──────────
        # Release ka type har passenger ki allocation (CNF/RAC/WL) se decide hota
        # hai, booking_status se nahi — taaki ek payment_pending (abhi-unpaid)
        # booking cancel hone par bhi uska held seat sahi se free ho.
        await self._release_booking_inventory(
            db=db,
            booking=booking,
            inventory=inventory,
        )

        # ── 6. Bookings → cancelled ───────────────────────────────────────────────
        booking.booking_status = BookingStatus.CANCELLED

        await db.flush()

        return {
            "booking_id": str(booking.id),
            "pnr_number": booking.pnr_number,
            "booking_status": booking.booking_status,
        }

    async def confirm_booking_after_payment(
        self,
        db: AsyncSession,
        booking: Bookings,
    ) -> None:
        """
        Payment success ke baad payment_pending booking ko uske final status par
        promote karo. Seat / RAC slot / WL position booking banते waqt hi HOLD ho
        chuka tha, isliye yahan sirf status flip hota hai — inventory counters ko
        haath nahi lagते.

        `booking.booking_passengers` eager-loaded hone chahiye.
        """
        if booking.booking_status not in (
            BookingStatus.INITIATED,
            BookingStatus.PAYMENT_PENDING,
        ):
            # Already final state (idempotent retry / legacy booking) — kuch nahi.
            return

        final_status_map = {
            PassengerStatus.CONFIRMED.value: BookingStatus.CONFIRMED,
            PassengerStatus.RAC.value: BookingStatus.RAC,
            PassengerStatus.WAITLISTED.value: BookingStatus.WAITLISTED,
        }
        held_status = next(
            (
                bp.passenger_status
                for bp in booking.booking_passengers
                if bp.passenger_status != PassengerStatus.CANCELLED
            ),
            None,
        )
        booking.booking_status = final_status_map.get(
            held_status, BookingStatus.CONFIRMED
        )

    async def release_booking_after_failed_payment(
        self,
        db: AsyncSession,
        booking: Bookings,
    ) -> None:
        """
        Payment fail hone par payment_pending booking ka HELD inventory release
        karo aur booking ko cancel karo. Logic cancel_booking jaisa hi hai, bas
        trigger user-request ki jagah payment-failure hai.

        `booking.booking_passengers` eager-loaded hone chahiye.
        """
        if booking.booking_status not in (
            BookingStatus.INITIATED,
            BookingStatus.PAYMENT_PENDING,
        ):
            # Booking already confirmed/cancelled — inventory ko mat chedo.
            return

        inventory = await self._fetch_inventory_with_lock(
            db=db,
            train_id=booking.train_id,
            journey_date=booking.journey_date,
            train_class=booking.train_class,
            quota=booking.quota,
        )
        await self._release_booking_inventory(
            db=db,
            booking=booking,
            inventory=inventory,
        )
        booking.booking_status = BookingStatus.CANCELLED

    async def view_receipt(
        self, booking_id: str, current_user_id, db: AsyncSession
    ) -> dict:
        result = await db.execute(
            select(Bookings)
            .options(
                selectinload(Bookings.train),
                selectinload(Bookings.source_station),
                selectinload(Bookings.destination_station),
                selectinload(Bookings.user).selectinload(Users.user_contact),
                selectinload(Bookings.user).selectinload(Users.user_profile),
                selectinload(Bookings.booking_passengers),
                selectinload(Bookings.payments),
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

        # Receipt me payment + personal data hai — sirf owner dekh sake.
        if str(booking.user_id) != str(current_user_id):
            raise RailMindException(
                code="RM-AUTH-005",
                message="Booking does not belong to current user",
                status_code=status.HTTP_403_FORBIDDEN,
            )

        # ── Boarding stop — departure time / distance ke liye ────────────────────
        stops_result = await db.execute(
            select(TrainStations)
            .where(TrainStations.train_id == booking.train_id)
            .order_by(TrainStations.sequence_number)
        )
        stops = stops_result.scalars().all()
        from_stop = next(
            (s for s in stops if s.station_id == booking.source_station_id), None
        )
        to_stop = next(
            (s for s in stops if s.station_id == booking.destination_station_id), None
        )

        # ── Line items (qty/rate/amount) + subtotal + GST ────────────────────────
        passenger_count = len(booking.booking_passengers) or 1
        line_items, subtotal, gst_total = await self._build_invoice_line_items(
            db=db,
            booking=booking,
            from_stop=from_stop,
            to_stop=to_stop,
            qty=passenger_count,
        )

        # ── Payment / status ─────────────────────────────────────────────────────
        payment = self._select_booking_payment(booking)
        invoice_dt = (
            payment.paid_at if payment and payment.paid_at else booking.booked_at
        )

        profile = booking.user.user_profile
        billed_name = (
            f"{profile.first_name} {profile.last_name}"
            if profile
            else booking.user.username
        )

        return {
            "invoice_no": f"RMP-{booking.booked_at.year}-{booking.pnr_number[-5:]}",
            "invoice_date": invoice_dt.strftime("%d %b %Y, %H:%M"),
            "pnr_number": booking.pnr_number,
            "status": self._receipt_status(payment),
            "seller": RECEIPT_SELLER_INFO,
            "billed_to": {
                "name": billed_name,
                "email": booking.user.email,
                "phone": (
                    booking.user.user_contact.mobile_number
                    if booking.user.user_contact
                    else "—"
                ),
            },
            "journey": {
                "train_number": booking.train.train_number,
                "train_name": booking.train.train_name,
                "from_station": booking.source_station.station_code,
                "from_station_name": booking.source_station.station_name,
                "to_station": booking.destination_station.station_code,
                "to_station_name": booking.destination_station.station_name,
                "train_class": booking.train_class,
                "train_class_label": TRAIN_CLASS_LABELS.get(
                    booking.train_class, booking.train_class
                ),
                "quota": booking.quota,
                "quota_label": QUOTA_LABELS.get(booking.quota, booking.quota),
                "journey_date": booking.journey_date.strftime("%a, %d %b %Y"),
                "departure_time": (
                    str(from_stop.departure_time)[:5] if from_stop else "—"
                ),
            },
            "line_items": line_items,
            "subtotal": subtotal,
            "gst": gst_total,
            "total_paid": round(booking.total_fare, 2),
            "currency": payment.currency if payment else "INR",
            "payment": {
                "method": (
                    payment.payment_method.value
                    if payment and payment.payment_method
                    else "—"
                ),
                "method_detail": (
                    payment.gateway_response.get("payment_detail")
                    if payment and payment.gateway_response
                    else None
                ),
                "transaction_id": (
                    (payment.gateway_payment_id or payment.gateway_order_id)
                    if payment
                    else "—"
                ),
                "gateway": payment.gateway.value.title() if payment else "—",
                "paid_at": (
                    payment.paid_at.isoformat() if payment and payment.paid_at else None
                ),
            },
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
                # payments — Txn details ke liye
                selectinload(Bookings.payments),
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

        # ── Distance, duration, arrival-day calculate karo ───────────────────────
        distance_km = 0
        if from_stop and to_stop:
            distance_km = to_stop.distance_km - from_stop.distance_km

        duration = self._format_journey_duration(from_stop, to_stop)

        arrival_day = None
        if from_stop and to_stop and to_stop.day_number > from_stop.day_number:
            arrival_day = f"+{to_stop.day_number - from_stop.day_number}"

        # ── Real fare breakdown (recompute) + payment/Txn details ────────────────
        fare_breakdown = await self._build_fare_breakdown(
            db=db,
            booking=booking,
            train_data=booking.train,
            from_stop=from_stop,
            to_stop=to_stop,
        )
        payment_info = self._build_payment_info(booking)

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
            "train_class": TRAIN_CLASS_LABELS.get(
                booking.train_class, booking.train_class
            ),
            "quota": QUOTA_LABELS.get(booking.quota, booking.quota),
            "source_station": booking.source_station.station_code,
            "source_name": booking.source_station.station_name,
            "departure_time": str(from_stop.departure_time)[:5] if from_stop else "—",
            "dest_station": booking.destination_station.station_code,
            "dest_name": booking.destination_station.station_name,
            "arrival_time": str(to_stop.arrival_time)[:5] if to_stop else "—",
            "arrival_day": arrival_day,
            "distance_km": f"{distance_km:,}",
            "duration": duration,
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
            "fare_breakdown": fare_breakdown,
            "payment": payment_info,
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

        # ── PDF generate karo ───────────────────────────────────────────────────
        # build_ticket_pdf in-memory canvas se PDF ke raw bytes return karta hai
        # (koi file disk pe likhne ki zaroorat nahi).
        pdf_bytes = build_ticket_pdf(ticket=ticket_payload)

        # ── Supabase pe upload karke public URL return karo ─────────────────────
        file_name = f"ticket_{booking.pnr_number}.pdf"
        public_url = upload_pdf_to_supabase(
            pdf_bytes=pdf_bytes,
            file_name=file_name,
        )

        return public_url

    async def get_fare_preview(
        self,
        payload: FarePreviewDTO,
        db: AsyncSession,
    ) -> dict:

        train_data, from_stop, to_stop = await train_service._validate_journey(
            payload.train_number,
            payload=payload,
            db=db,
        )

        # Per-passenger fare breakdown
        fare = await common_service.calculate_fare(
            db=db,
            train_type=train_data.train_type,
            train_class=payload.train_class,
            from_stop=from_stop,
            to_stop=to_stop,
            quota=payload.quota,
            include_irctc_charge=True,
        )

        count = payload.passenger_count

        return {
            "base_fare": fare.base_fare,
            "passenger_count": count,
            "reservation_charge": fare.reservation_charge,
            "superfast_charge": fare.superfast_charge,
            "tatkal_charge": fare.tatkal_charge,
            "gst": fare.gst_amount,
            "irctc_charge": fare.irctc_service_charge,
            "total_fare": round(fare.total_fare * count, 2),
        }

    @staticmethod
    def _format_journey_duration(from_stop, to_stop) -> str:
        """
        Departure/arrival time (HH:MM strings) + day_number se total journey
        duration "Xh YYm" format me. Data missing/invalid ho to "—".
        """
        if not (
            from_stop and to_stop and from_stop.departure_time and to_stop.arrival_time
        ):
            return "—"

        try:
            dep = str(from_stop.departure_time)
            arr = str(to_stop.arrival_time)
            dep_minutes = int(dep[:2]) * 60 + int(dep[3:5])
            arr_minutes = int(arr[:2]) * 60 + int(arr[3:5])
        except (ValueError, IndexError):
            return "—"

        dep_total = (from_stop.day_number - 1) * 1440 + dep_minutes
        arr_total = (to_stop.day_number - 1) * 1440 + arr_minutes
        diff = arr_total - dep_total
        if diff < 0:
            diff += 1440  # day_number data galat ho to bhi crash na ho

        hours, minutes = divmod(diff, 60)
        return f"{hours}h {minutes:02d}m"

    async def _build_fare_breakdown(
        self,
        db: AsyncSession,
        booking: Bookings,
        train_data,
        from_stop,
        to_stop,
    ) -> dict:
        """
        Booking-level fare breakdown — per-passenger fare recompute karke
        passenger count se multiply. Booking sirf total_fare store karti hai,
        isliye components yahan dobara nikalte hain (booking ke time wali hi
        config: include_irctc_charge=True, no age/gender). Recompute fail ho to
        safe fallback (base = total).
        """
        passenger_count = len(booking.booking_passengers) or 1

        fallback = {
            "base_fare": booking.total_fare,
            "reservation_charge": 0.0,
            "superfast_charge": 0.0,
            "gst": 0.0,
            "insurance": 0.0,
            "total_fare": booking.total_fare,
        }

        if not (from_stop and to_stop):
            return fallback

        try:
            per = await common_service.calculate_fare(
                db=db,
                train_type=train_data.train_type,
                train_class=booking.train_class,
                from_stop=from_stop,
                to_stop=to_stop,
                quota=booking.quota,
                include_irctc_charge=True,
            )
        except RailMindException:
            return fallback

        n = passenger_count
        return {
            "base_fare": round(per.base_fare * n, 2),
            "reservation_charge": round(per.reservation_charge * n, 2),
            "superfast_charge": round(per.superfast_charge * n, 2),
            "tatkal_charge": round(per.tatkal_charge * n, 2),
            "gst": round(per.gst_amount * n, 2),
            "irctc_service_charge": round(per.irctc_service_charge * n, 2),
            "insurance": 0.0,
            # Displayed total = booking pe actually charge hua amount (authoritative).
            "total_fare": booking.total_fare,
        }

    @staticmethod
    def _select_booking_payment(booking: Bookings):
        """
        Booking ke payments me se SUCCESS wala (warna latest attempt) Payment
        object return karo, ya None agar koi payment hi nahi.
        """
        if not booking.payments:
            return None
        return next(
            (p for p in booking.payments if p.payment_status == PaymentStatus.SUCCESS),
            None,
        ) or max(booking.payments, key=lambda p: p.initiated_at)

    @staticmethod
    def _build_payment_info(booking: Bookings) -> dict:
        """
        PDF ticket ke liye Txn / method / status. Koi payment na ho to "—".
        """
        chosen = BookingService._select_booking_payment(booking)
        if not chosen:
            return {"txn_id": "—", "method": "—", "status": "—"}

        return {
            "txn_id": chosen.gateway_payment_id or chosen.gateway_order_id or "—",
            "method": chosen.payment_method.value if chosen.payment_method else "—",
            "status": (
                chosen.payment_status.value.upper() if chosen.payment_status else "—"
            ),
        }

    @staticmethod
    def _receipt_status(payment) -> str:
        """Payment se receipt-level status (PAID / PENDING / REFUNDED / UNPAID)."""
        if not payment:
            return "UNPAID"
        return {
            PaymentStatus.SUCCESS: "PAID",
            PaymentStatus.PENDING: "PENDING",
            PaymentStatus.PROCESSING: "PENDING",
            PaymentStatus.REFUNDED: "REFUNDED",
            PaymentStatus.FAILED: "UNPAID",
        }.get(payment.payment_status, "UNPAID")

    async def _build_invoice_line_items(
        self,
        db: AsyncSession,
        booking: Bookings,
        from_stop,
        to_stop,
        qty: int,
    ) -> tuple[list[dict], float, float]:
        """
        Per-passenger fare recompute karke invoice line items (description / qty
        / rate / amount) banao. Returns (line_items, subtotal, gst).

        - rate = per-passenger component, amount = rate × qty (jaisa booking pe
          actually charge hua — har component per passenger).
        - subtotal = line items ka sum (GST chhod ke); gst alag (AC classes pe > 0).
        - Recompute fail / stops missing → single base-fare line = total_fare.
        """
        class_label = TRAIN_CLASS_LABELS.get(booking.train_class, booking.train_class)

        def _fallback() -> tuple[list[dict], float, float]:
            amount = round(booking.total_fare, 2)
            return (
                [
                    {
                        "description": f"Base fare — {class_label}",
                        "qty": qty,
                        "rate": round(amount / qty, 2) if qty else amount,
                        "amount": amount,
                    }
                ],
                amount,
                0.0,
            )

        if not (from_stop and to_stop):
            return _fallback()

        try:
            per = await common_service.calculate_fare(
                db=db,
                train_type=booking.train.train_type,
                train_class=booking.train_class,
                from_stop=from_stop,
                to_stop=to_stop,
                quota=booking.quota,
                include_irctc_charge=True,
            )
        except RailMindException:
            return _fallback()

        # (description, per-passenger rate, always_show)
        components = [
            (f"Base fare — {class_label}", per.base_fare, True),
            ("Reservation charge", per.reservation_charge, False),
            ("Superfast charge", per.superfast_charge, False),
            ("Tatkal charge", per.tatkal_charge, False),
            ("IRCTC convenience fee", per.irctc_service_charge, False),
        ]

        line_items = [
            {
                "description": desc,
                "qty": qty,
                "rate": round(rate, 2),
                "amount": round(rate * qty, 2),
            }
            for desc, rate, always in components
            if always or rate > 0
        ]

        subtotal = round(sum(li["amount"] for li in line_items), 2)
        gst_total = round(per.gst_amount * qty, 2)
        return line_items, subtotal, gst_total

    async def upcoming_and_past_journey_details(
        self,
        action,
        current_user_id: str,
        db: AsyncSession,
    ) -> dict:

        booking_list = await self.get_all_user_bookings(current_user_id, db)

        today = date.today()

        if action == JourneyActionType.UPCOMING:

            journey_result = [
                booking for booking in booking_list if booking["journey_date"] >= today
            ]

        elif action == JourneyActionType.PAST:

            journey_result = [
                booking for booking in booking_list if booking["journey_date"] < today
            ]

        else:
            journey_result = []

        return {
            "count": len(journey_result),
            "journeys": journey_result,
        }

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

    async def _release_booking_inventory(
        self,
        db: AsyncSession,
        booking: Bookings,
        inventory: SeatInventories,
    ) -> None:
        """
        Booking jo inventory hold kar rahi hai use release karo aur downstream
        promotion cascade chalao. Release ka type har passenger ki allocation
        (CNF / RAC / WL) se decide hota hai — booking_status se nahi — taaki yeh
        dono case me kaam kare:
            • confirmed booking ka cancellation         (passengers = CNF)
            • payment_pending booking ka payment fail    (passengers CNF/RAC/WL)

        Caller `inventory` ko row-lock (SELECT FOR UPDATE) ke saath fetch kare aur
        booking ka final status (cancelled waghera) khud set kare.
        `booking.booking_passengers` eager-loaded hone chahiye.
        """
        active_passengers = [
            bp
            for bp in booking.booking_passengers
            if bp.passenger_status != PassengerStatus.CANCELLED
        ]
        if not active_passengers:
            return

        # Ek booking ke saare passengers ki allocation same hoti hai.
        held_status = active_passengers[0].passenger_status
        passenger_count = len(active_passengers)

        # Passengers → CAN, seat free karo
        for bp in active_passengers:
            bp.passenger_status = PassengerStatus.CANCELLED
            bp.seat_id = None
            bp.allotted_berth = None

        if held_status == PassengerStatus.CONFIRMED:
            inventory.available_confirmed_seats += passenger_count
            # Promotion cascade — RAC → CNF, WL → RAC
            await self._run_promotion_cascade(
                db=db,
                inventory=inventory,
                freed_count=passenger_count,
            )

        elif held_status == PassengerStatus.RAC:
            inventory.available_rac_slots += passenger_count
            # RACSlots clean up — ondelete SET NULL handles passenger FKs
            await self._clear_rac_slots(
                db=db,
                inventory=inventory,
                booking_passengers=active_passengers,
            )
            # WL → RAC promote karo
            await self._promote_wl_to_rac(
                db=db,
                inventory=inventory,
                count=passenger_count,
            )

        elif held_status == PassengerStatus.WAITLISTED:
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
    ) -> tuple[Bookings, list[BookingPassengers], list[str | None]]:
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

        logger.info(
            "_create_booking_records called; thread=%s; loop=%s",
            threading.current_thread().name,
            asyncio.get_running_loop(),
        )
        # ── Booking status ────────────────────────────────────────────────────────
        # Pay-first lifecycle: inventory yahin HOLD ho jaata hai (neeche counters
        # decrement + seat physically allocate hoti hai), lekin booking khud tab
        # tak `payment_pending` rehti hai jab tak payment success na ho. Intended
        # allocation (CNF / RAC / WL) har BookingPassenger ke passenger_status par
        # carry hoti hai, isliye:
        #   • payment success → PaymentService booking ko uske final
        #     confirmed/rac/waitlisted status par promote karta hai
        #     (confirm_booking_after_payment)
        #   • payment failure → held inventory release ho jaata hai
        #     (release_booking_after_failed_payment)
        booking_status = BookingStatus.PAYMENT_PENDING.value

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
        logger.info(
            "booking row added (pending flush); thread=%s; loop=%s",
            threading.current_thread().name,
            asyncio.get_running_loop(),
        )
        await db.flush()
        logger.info(
            "db.flush() completed; booking id=%s; thread=%s; loop=%s",
            booking.id,
            threading.current_thread().name,
            asyncio.get_running_loop(),
        )
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
        seat_numbers: list[str | None] = []
        for i, (passenger, fare) in enumerate(zip(payload.passengers, fares)):
            seat = assigned_seats[i] if assigned_seats else None
            seat_numbers.append(seat.Seats.seat_number if seat else None)

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

        return booking, booking_passengers, seat_numbers

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
        allow_wl_to_rac: bool = True,
    ) -> None:
        """CNF cancel → RAC promote → WL promote.

        allow_wl_to_rac=False (chart Stage 2) does RAC→CNF only and skips the
        WL→RAC step (Stage 1 has already cleared the waitlist).
        """
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
                    # The freed CNF seat is now taken by the promoted RAC
                    # passenger — without this the inventory shows a phantom
                    # free seat (overbooking risk in both cancel and chart prep).
                    inventory.available_confirmed_seats -= 1
                    rac_slot.passenger_1_booking_passenger_id = (
                        rac_slot.passenger_2_booking_passenger_id
                    )
                    rac_slot.passenger_2_booking_passenger_id = None
                    rac_slot.is_full = False
                    inventory.available_rac_slots += 1

                    # WL/1 → RAC
                    if allow_wl_to_rac:
                        await self._promote_wl_to_rac(
                            db=db, inventory=inventory, count=1
                        )

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
