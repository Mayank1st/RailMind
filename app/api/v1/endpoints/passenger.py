from fastapi import APIRouter
from fastapi import APIRouter, Depends
from uuid import UUID
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_db, get_redis
from app.core.response import ok, created

from app.schemas.Request.passengerRequestDTO import (
    CreatePassengerDTO,
    UpdatePassengerDTO,
)
from app.services.passenger_service import PassengerService

passenger_service = PassengerService()


router = APIRouter(prefix="/passenger", tags=["Passenger"])


@router.post("")
async def create_passenger(
    payload: CreatePassengerDTO,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    data = await passenger_service.create_passenger(
        payload=payload,
        current_user_id=current_user["sub"],
        db=db,
    )
    return created(
        data=data,
        message=f"Passenger created successfully.",
    )


@router.get("")
async def passenger_list(
    db: AsyncSession = Depends(get_db), current_user: dict = Depends(get_current_user)
):
    data = await passenger_service.passenger_list(
        current_user_id=current_user["sub"],
        db=db,
    )
    return ok(
        data=data,
        message=f"Passenger created successfully.",
    )


@router.patch("/{passenger_id}")
async def update_passenger(
    passenger_id: UUID,
    payload: UpdatePassengerDTO,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    data = await passenger_service.update_passenger(
        passenger_id,
        payload,
        current_user_id=current_user["sub"],
        db=db,
    )
    return ok(
        data=data,
        message=f"Passenger Updated Successfully.",
    )


@router.delete("/{passenger_id}")
async def delete_passenger(
    passenger_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    data = await passenger_service.delete_passenger(
        passenger_id,
        current_user_id=current_user["sub"],
        db=db,
    )
    return ok(
        data=data,
        message=f"Passenger Deleted Successfully.",
    )
