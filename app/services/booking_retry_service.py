from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import UUID

from fastapi import status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.exceptions import RailMindException
from app.core.constants.booking_retry_request import (
    BookingRetryRequestStatus,
    RetryFailureReason,
)
from app.db.models.booking import Bookings, BookingPassengers
from app.db.models.booking_retry_requests import BookingRetryRequest

IMMEDIATE_RETRY_INTERVALS = [30, 60, 120]
SCHEDULED_RETRY_HOURS = [23, 6, 0]  # 11PM, 6AM, midnight


class BookingRetryService:

    async def create_retry_request(
        self,
        booking_id: UUID,
        current_user_id: str,
        db: AsyncSession,
    ) -> dict:
        # ── Booking fetch + validate ──────────────────────────────────────────
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

        # ── Already an active retry? ──────────────────────────────────────────
        existing = await db.execute(
            select(BookingRetryRequest).where(
                BookingRetryRequest.booking_id == booking_id,
                BookingRetryRequest.status.in_(
                    [
                        BookingRetryRequestStatus.PENDING,
                        BookingRetryRequestStatus.RETRYING,
                    ]
                ),
            )
        )
        if existing.scalar_one_or_none():
            raise RailMindException(
                code="RM-BKG-007",
                message="A retry is already in progress for this booking",
                status_code=status.HTTP_409_CONFLICT,
            )

        # ── Failure reason — booking status se detect karo ───────────────────
        failure_reason = (
            RetryFailureReason.PAYMENT_TIMEOUT
            if booking.booking_status == "payment_failed"
            else RetryFailureReason.SEAT_UNAVAILABLE
        )

        # ── Original payload reconstruct karo from DB ─────────────────────────
        # CreateBookingDTO ke fields match karte hain
        original_payload = {
            "train_number": None,  # train join se milega — Celery mein fetch hoga
            "journey_date": str(booking.journey_date),
            "from_station": None,  # source_station join se milega
            "to_station": None,  # destination_station join se milega
            "train_class": booking.train_class,
            "quota": booking.quota,
            "passengers": [
                {
                    "passenger_id": str(bp.passenger_id),
                    "berth_preference": bp.berth_preference,
                }
                for bp in booking.booking_passengers
            ],
            # IDs store karte hain taaki Celery join avoid kar sake
            "_meta": {
                "train_id": str(booking.train_id),
                "source_station_id": str(booking.source_station_id),
                "destination_station_id": str(booking.destination_station_id),
                "original_booking_id": str(booking.id),
            },
        }

        # ── First retry 30 seconds baad ───────────────────────────────────────
        next_retry_at = datetime.now(timezone.utc) + timedelta(
            seconds=IMMEDIATE_RETRY_INTERVALS[0]
        )

        retry_request = BookingRetryRequest(
            booking_id=booking_id,
            user_id=current_user_id,
            failure_reason=failure_reason,
            original_payload=original_payload,
            status=BookingRetryRequestStatus.PENDING,
            attempt_count=0,
            max_attempts=6,
            next_retry_at=next_retry_at,
        )

        db.add(retry_request)
        await db.flush()
        await db.refresh(retry_request)

        return {
            "retry_request_id": str(retry_request.id),
            "booking_id": str(booking_id),
            "status": retry_request.status,
            "failure_reason": retry_request.failure_reason,
            "attempt_count": retry_request.attempt_count,
            "max_attempts": retry_request.max_attempts,
            "next_retry_at": retry_request.next_retry_at.isoformat(),
        }

    async def get_retry_status(
        self,
        booking_id: UUID,
        current_user_id: str,
        db: AsyncSession,
    ) -> dict:
        """Latest retry request ka status return karo."""
        result = await db.execute(
            select(BookingRetryRequest)
            .where(BookingRetryRequest.booking_id == booking_id)
            .order_by(BookingRetryRequest.created_at.desc())
            .limit(1)
        )
        retry_request = result.scalar_one_or_none()

        if not retry_request:
            raise RailMindException(
                code="RM-BKG-008",
                message="No retry request found for this booking",
                status_code=status.HTTP_404_NOT_FOUND,
            )

        return {
            "retry_request_id": str(retry_request.id),
            "booking_id": str(booking_id),
            "status": retry_request.status,
            "failure_reason": retry_request.failure_reason,
            "attempt_count": retry_request.attempt_count,
            "max_attempts": retry_request.max_attempts,
            "last_attempted_at": (
                retry_request.last_attempted_at.isoformat()
                if retry_request.last_attempted_at
                else None
            ),
            "next_retry_at": (
                retry_request.next_retry_at.isoformat()
                if retry_request.next_retry_at
                else None
            ),
            "success_booking_id": (
                str(retry_request.success_booking_id)
                if retry_request.success_booking_id
                else None
            ),
        }

    async def update_retry_attempt(
        self,
        retry_request_id: str,
        success: bool,
        db: AsyncSession,
        success_booking_id: str | None = None,
    ) -> dict:
        result = await db.execute(
            select(BookingRetryRequest).where(
                BookingRetryRequest.id == retry_request_id
            )
        )
        retry_request = result.scalar_one_or_none()
        if not retry_request:
            return {"action": "not_found"}

        now = datetime.now(timezone.utc)
        retry_request.attempt_count += 1
        retry_request.last_attempted_at = now

        if success:
            retry_request.status = BookingRetryRequestStatus.SUCCESS
            retry_request.success_booking_id = success_booking_id
            retry_request.next_retry_at = None
            return {"action": "success"}

        attempt = retry_request.attempt_count

        # ── Immediate retries: attempts 1, 2, 3 ──────────────────────────────
        if attempt < len(IMMEDIATE_RETRY_INTERVALS):
            delay = IMMEDIATE_RETRY_INTERVALS[attempt]
            retry_request.status = BookingRetryRequestStatus.RETRYING
            retry_request.next_retry_at = now + timedelta(seconds=delay)
            return {"action": "retry_immediate", "countdown": delay}

        # ── Scheduled retries: attempts 4, 5, 6 ──────────────────────────────
        scheduled_index = attempt - len(IMMEDIATE_RETRY_INTERVALS)
        if scheduled_index < len(SCHEDULED_RETRY_HOURS):
            next_dt = self._next_scheduled_time(SCHEDULED_RETRY_HOURS[scheduled_index])
            retry_request.status = BookingRetryRequestStatus.RETRYING
            retry_request.next_retry_at = next_dt
            eta_seconds = int((next_dt - now).total_seconds())
            return {"action": "retry_scheduled", "countdown": eta_seconds}

        # ── Exhausted ─────────────────────────────────────────────────────────
        retry_request.status = BookingRetryRequestStatus.EXHAUSTED
        retry_request.next_retry_at = None
        return {"action": "exhausted"}

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _next_scheduled_time(self, hour_ist: int) -> datetime:
        from pytz import timezone as pytz_tz

        ist = pytz_tz("Asia/Kolkata")
        now_ist = datetime.now(ist)
        target = now_ist.replace(hour=hour_ist, minute=0, second=0, microsecond=0)
        if target <= now_ist:
            target += timedelta(days=1)
        return target.astimezone(timezone.utc)
