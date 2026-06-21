from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_
from fastapi import status

from app.core.exceptions import RailMindException
from app.domain.passenger.dto.passenger_request_dto import (
    CreatePassengerDTO,
    UpdatePassengerDTO,
)
from app.domain.passenger.dto.passenger_response_dto import (
    PassengerResponseDTO,
    PassengerListResponseDTO,
)
from app.db.models.passengers import Passengers


class PassengerService:
    async def create_passenger(
        self,
        payload: CreatePassengerDTO,
        current_user_id,
        db: AsyncSession,
    ) -> dict:

        if payload.is_primary:
            result = await db.execute(
                select(Passengers).where(
                    Passengers.user_id == current_user_id,
                    Passengers.is_primary == True,
                )
            )
            existing_primary = result.scalar_one_or_none()

            if existing_primary:
                raise RailMindException(
                    code="RM-PSG-001",
                    message="You already have a primary passenger",
                    status_code=status.HTTP_409_CONFLICT,
                )

        new_passenger = Passengers(
            user_id=current_user_id,
            full_name=payload.full_name,
            age=payload.age,
            gender=payload.gender,
            id_type=payload.id_type,
            id_number=payload.id_number,
            berth_preference=payload.berth_preference,
            is_primary=payload.is_primary,
        )

        db.add(new_passenger)
        await db.flush()

        return PassengerResponseDTO.model_validate(new_passenger)

    async def passenger_list(
        self, current_user_id, db: AsyncSession
    ) -> PassengerListResponseDTO:
        result = await db.execute(
            select(Passengers).where(Passengers.user_id == current_user_id)
        )

        passengers_list = result.scalars().all()

        if len(passengers_list) == 0:
            raise RailMindException(
                code="RM-PSG-002",
                message="No Record Found For Passengers",
                status_code=status.HTTP_204_NO_CONTENT,
            )
        return PassengerListResponseDTO.model_validate(
            {"total": len(passengers_list), "passengers": passengers_list}
        )

    async def update_passenger(
        self,
        passenger_id,
        payload: UpdatePassengerDTO,
        current_user_id,
        db: AsyncSession,
    ) -> dict:
        result = await db.execute(
            select(Passengers).where(
                and_(
                    Passengers.user_id == current_user_id, Passengers.id == passenger_id
                )
            )
        )

        existing_passenger = result.scalar_one_or_none()

        if existing_passenger is None:
            raise RailMindException(
                code="RM-PSG-003",
                message="No Record Found For Passengers",
                status_code=status.HTTP_204_NO_CONTENT,
            )

        updated_data = payload.model_dump(exclude_unset=True)
        for field, value in updated_data.items():
            setattr(existing_passenger, field, value)

        await db.flush()
        return PassengerResponseDTO.model_validate(existing_passenger)

    async def delete_passenger(
        self, passenger_id, current_user_id, db: AsyncSession
    ) -> dict:
        result = await db.execute(
            select(Passengers).where(
                and_(
                    Passengers.user_id == current_user_id, Passengers.id == passenger_id
                )
            )
        )

        existing_passenger = result.scalar_one_or_none()

        if existing_passenger is None:
            raise RailMindException(
                code="RM-PSG-004",
                message="No Record Found For Passengers",
                status_code=status.HTTP_404_NOT_FOUND,
            )

        existing_passenger.is_active = False
        await db.commit()
        await db.refresh(existing_passenger)

        return {}
