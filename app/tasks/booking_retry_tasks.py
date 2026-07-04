from __future__ import annotations

import traceback

from celery.utils.log import get_task_logger
from sqlalchemy import select

from app.db.models.booking_retry_requests import BookingRetryRequest
from app.db.models.train import Stations, Trains
from app.db.session import async_session_local
from app.domain.booking.booking_service.booking_retry_service import (
    BookingRetryService,
)
from app.domain.booking.booking_service.booking_service import BookingService
from app.domain.booking.constants.booking_retry_request import RetryFailureReason
from app.domain.booking.dto.booking_request_dto import (
    CreateBookingDTO,
    PassengerBookingDTO,
)
from app.tasks import notification_tasks as _notification_tasks
from app.tasks.celery_app import celery_app
from app.tasks.worker_loop import run_in_worker_loop as _run_in_worker_loop

logger = get_task_logger(__name__)


async def _async_retry_booking(retry_request_id: str) -> None:
    retry_service = BookingRetryService()
    booking_service = BookingService()

    async with async_session_local() as db:

        # ── Fetch retry request ───────────────────────────────────────────────
        result = await db.execute(
            select(BookingRetryRequest).where(
                BookingRetryRequest.id == retry_request_id
            )
        )
        retry_request = result.scalar_one_or_none()
        if not retry_request:
            logger.warning(
                "Retry request not found. Skipping task. retry_request_id=%s",
                retry_request_id,
            )
            return

        payload = retry_request.original_payload
        meta = payload.get("_meta", {})
        user_id = str(retry_request.user_id)
        logger.warning(
            "Starting retry attempt. retry_request_id=%s attempt_count=%s",
            retry_request_id,
            retry_request.attempt_count + 1,
        )

        success = False
        new_booking_id = None

        try:
            if retry_request.failure_reason == RetryFailureReason.SEAT_UNAVAILABLE:

                # ── Train + station codes fetch karo ──────────────────────────
                train_result = await db.execute(
                    select(Trains).where(Trains.id == meta["train_id"])
                )
                train = train_result.scalar_one_or_none()

                src_result = await db.execute(
                    select(Stations).where(Stations.id == meta["source_station_id"])
                )
                src = src_result.scalar_one_or_none()

                dst_result = await db.execute(
                    select(Stations).where(
                        Stations.id == meta["destination_station_id"]
                    )
                )
                dst = dst_result.scalar_one_or_none()

                if not train or not src or not dst:
                    raise Exception("Train or station data missing")

                # ── CreateBookingDTO reconstruct karo ─────────────────────────
                booking_dto = CreateBookingDTO(
                    train_number=train.train_number,
                    journey_date=payload["journey_date"],
                    from_station=src.station_code,
                    to_station=dst.station_code,
                    train_class=payload["train_class"],
                    quota=payload["quota"],
                    passengers=[
                        PassengerBookingDTO(
                            passenger_id=p["passenger_id"],
                            berth_preference=p["berth_preference"],
                        )
                        for p in payload["passengers"]
                    ],
                )

                # ── Booking attempt ───────────────────────────────────────────
                new_booking = await booking_service.create_booking(
                    payload=booking_dto,
                    current_user_id=user_id,
                    db=db,
                )
                success = True
                new_booking_id = str(new_booking["booking_id"])

            elif retry_request.failure_reason == RetryFailureReason.PAYMENT_TIMEOUT:
                # Payment service banega tab wire karenge
                success = False

        except Exception as e:
            print("RETRY ERROR:", str(e))
            traceback.print_exc()
            success = False

        # ── Update retry state — NO db.begin(), autobegin already active ─────
        next_action = await retry_service.update_retry_attempt(
            retry_request_id=retry_request_id,
            success=success,
            db=db,
            success_booking_id=new_booking_id,
        )
        await db.commit()  # ← single commit at the end

        # ── Handle next action ────────────────────────────────────────────────
        action = next_action.get("action")
        countdown = next_action.get("countdown", 30)
        logger.warning(
            "Retry action decided. retry_request_id=%s action=%s countdown=%s",
            retry_request_id,
            action,
            countdown,
        )

        if action == "success":
            _notification_tasks.task_send_retry_success_email.delay(
                user_id=user_id,
                booking_id=new_booking_id,
            )

        elif action in ("retry_immediate", "retry_scheduled"):
            task_auto_retry_booking.apply_async(
                args=[retry_request_id],
                countdown=countdown,
            )

        elif action == "exhausted":
            _notification_tasks.task_send_retry_exhausted_email.delay(
                user_id=user_id,
                booking_id=meta.get("original_booking_id"),
            )


@celery_app.task(
    name="booking_tasks.task_auto_retry_booking",
    bind=True,
    max_retries=0,  # Manual retry logic upar hai
)
def task_auto_retry_booking(self, retry_request_id: str) -> None:
    _run_in_worker_loop(_async_retry_booking(retry_request_id))
