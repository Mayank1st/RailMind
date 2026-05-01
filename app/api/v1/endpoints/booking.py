from uuid import UUID
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.booking_service import BookingService
from app.schemas.Request.bookingRequestDTO import CreateBookingDTO
from app.api.deps import get_current_user, get_db, get_redis
from app.core.response import APIResponse, created, ok


router = APIRouter(prefix="/bookings", tags=["Booking"])

booking_service = BookingService()


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


@router.get("/")
async def list_user_bookings(
    db: AsyncSession = Depends(get_db), current_user: dict = Depends(get_current_user)
):
    data = await booking_service.list_user_bookings(
        current_user_id=current_user["sub"],
        db=db,
    )
    return ok(
        data=data,
        message=f"User Booking List Fetched successfully.",
    )


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


@router.get("/{booking_id}/receipt")
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
