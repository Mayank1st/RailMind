from uuid import UUID
from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.booking.booking_service.booking_service import BookingService
from app.domain.booking.constants.booking import JourneyActionType, BookingJourneyFilter
from app.core.pagination import BookingParams, paginated
from app.domain.booking.booking_service.booking_retry_service import BookingRetryService
from app.domain.booking.booking_service.booking_retry_service import (
    IMMEDIATE_RETRY_INTERVALS,
)
from app.domain.booking.dto.booking_request_dto import (
    CreateBookingDTO,
    JourneyDTO,
    FarePreviewDTO,
)
from app.api.deps import get_current_user, get_db, get_redis
from app.core.response import created, ok
from app.tasks.booking_retry_tasks import task_auto_retry_booking

router = APIRouter(prefix="/bookings", tags=["Booking"])

booking_service = BookingService()
booking_retry_service = BookingRetryService()


@router.post("/")
async def create_booking(
    payload: CreateBookingDTO,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    data = await booking_service.create_booking(
        payload=payload,
        current_user_id=current_user["sub"],
        db=db,
    )
    return created(
        data=data,
        message=f"Booking for train {payload.train_number} created successfully.",
    )


@router.post("/fare-preview")
async def get_fare_preview(
    payload: FarePreviewDTO,
    db: AsyncSession = Depends(get_db),
):
    data = await booking_service.get_fare_preview(
        payload,
        db=db,
    )
    return ok(data=data, message="Fare Preview fetched successfully.")


@router.get("/")
async def list_user_bookings(
    filter: BookingJourneyFilter = Query(
        BookingJourneyFilter.ALL,
        description="Filter bookings by UPCOMING, COMPLETED, CANCELLED or ALL",
    ),
    params: BookingParams = Depends(),
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    page = await booking_service.list_user_bookings(
        current_user_id=current_user["sub"],
        db=db,
        journey_filter=filter,
        params=params,
    )
    return paginated(page, message="User Booking List Fetched successfully.")


@router.get("/upcoming-and-past-journey")
async def upcoming_and_past_journey_details(
    action: JourneyActionType,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    data = await booking_service.upcoming_and_past_journey_details(
        action=action,
        current_user_id=current_user["sub"],
        db=db,
    )
    return ok(data=data, message="Journey Details fetched successfully.")


@router.get("/{booking_id}")
async def get_booking_details_by_id(
    booking_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    data = await booking_service.get_booking_details_by_id(
        booking_id,
        current_user_id=current_user["sub"],
        db=db,
    )
    return ok(
        data=data,
        message=f"User Booking List Fetched successfully.",
    )


@router.post("/{booking_id}/cancel")
async def cancel_booking(
    booking_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    data = await booking_service.cancel_booking(
        booking_id,
        current_user_id=current_user["sub"],
        db=db,
    )
    return ok(
        data=data,
        message=f"User Booking Cancelled Fetched successfully.",
    )


@router.get("/{booking_id}/view-receipt")
async def view_receipt(
    booking_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    data = await booking_service.view_receipt(
        booking_id,
        current_user_id=current_user["sub"],
        db=db,
    )
    return ok(
        data=data,
        message=f"Receipt Fetched Successfully.",
    )


@router.post("/{booking_id}/receipt")
async def download_receipt(
    booking_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    data = await booking_service.download_receipt(
        booking_id,
        current_user_id=current_user["sub"],
        db=db,
    )
    return created(
        data=data,
        message=f"Ticket Downloaded Successfully.",
    )


@router.post("/{booking_id}/retry")
async def retry_booking(
    booking_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    data = await booking_retry_service.create_retry_request(
        booking_id=booking_id,
        current_user_id=current_user["sub"],
        db=db,
    )

    await db.commit()

    task_auto_retry_booking.apply_async(
        args=[data["retry_request_id"]],
        countdown=IMMEDIATE_RETRY_INTERVALS[0],
    )

    return created(
        data=data,
        message="Retry scheduled. We will notify you when the booking will be confirmed.",
    )


@router.get("/{booking_id}/retry-status")
async def get_retry_status(
    booking_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    data = await booking_retry_service.get_retry_status(
        booking_id=booking_id,
        current_user_id=current_user["sub"],
        db=db,
    )
    return ok(data=data, message="Retry status fetched successfully.")


#  payload: JourneyDTO,
