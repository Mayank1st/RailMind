from datetime import date
from typing import Annotated, Optional
from pydantic import Field, field_validator
from uuid import UUID

from app.schemas.base import BaseDTO
from app.core.constants.train import TrainClass, Quota
from app.core.constants.booking import BerthPreference
from app.core.constants.booking import (
    MAX_PASSENGERS_PER_BOOKING,
    MAX_PASSENGERS_PER_TATKAL_BOOKING,
)


class PassengerBookingDTO(BaseDTO):
    passenger_id: Annotated[UUID, Field(examples=["uuid-here"])]
    berth_preference: Annotated[
        BerthPreference,
        Field(default=BerthPreference.NO_PREFERENCE, examples=[BerthPreference.LOWER]),
    ]


class CreateBookingDTO(BaseDTO):
    train_number: Optional[Annotated[str, Field(examples=["12951"])]] = None
    journey_date: Annotated[date, Field(examples=["2026-05-01"])]
    from_station: Annotated[str, Field(examples=["NDLS"])]
    to_station: Annotated[str, Field(examples=["BCT"])]
    train_class: Annotated[TrainClass, Field(examples=[TrainClass.SLEEPER])]
    quota: Annotated[Quota, Field(default=Quota.GENERAL, examples=[Quota.GENERAL])]
    passengers: Annotated[
        list[PassengerBookingDTO],
        Field(
            min_length=1,
            max_length=MAX_PASSENGERS_PER_BOOKING,
            examples=[
                {
                    "passenger_id": "123e4567-e89b-12d3-a456-426614174000",
                    "berth_preference": "LOWER",
                }
            ],
        ),
    ]

    @field_validator("passengers")
    @classmethod
    def validate_passenger_count(
        cls, passengers: list[PassengerBookingDTO], info
    ) -> list[PassengerBookingDTO]:
        quota = info.data.get("quota")

        # Tatkal mein max 4 passengers
        if quota in (Quota.TATKAL, Quota.PREMIUM_TATKAL):
            if len(passengers) > MAX_PASSENGERS_PER_TATKAL_BOOKING:
                raise ValueError(
                    f"Maximum {MAX_PASSENGERS_PER_TATKAL_BOOKING} passengers allowed for Tatkal booking"
                )

        # Duplicate passenger_id check
        passenger_ids = [p.passenger_id for p in passengers]
        if len(passenger_ids) != len(set(passenger_ids)):
            raise ValueError("Duplicate passengers not allowed in a single booking")

        return passengers


class JourneyDTO(BaseDTO):
    train_number: Optional[Annotated[str, Field(examples=["12951"])]] = None
    journey_date: Annotated[date, Field(examples=["2026-05-01"])]
    from_station: Annotated[str, Field(examples=["NDLS"])]
    to_station: Annotated[str, Field(examples=["BCT"])]
    train_class: Annotated[TrainClass, Field(examples=[TrainClass.SLEEPER])]
    quota: Annotated[Quota, Field(default=Quota.GENERAL, examples=[Quota.GENERAL])]
    passengers: Annotated[
        list[PassengerBookingDTO],
        Field(
            min_length=1,
            max_length=MAX_PASSENGERS_PER_BOOKING,
            examples=[
                {
                    "passenger_id": "123e4567-e89b-12d3-a456-426614174000",
                    "berth_preference": "LOWER",
                }
            ],
        ),
    ]


class FarePreviewDTO(BaseDTO):
    train_number: Optional[Annotated[str, Field(examples=["12951"])]] = None
    journey_date: Annotated[date, Field(examples=["2026-05-01"])]
    from_station: Annotated[str, Field(examples=["NDLS"])]
    to_station: Annotated[str, Field(examples=["BCT"])]
    train_class: Annotated[TrainClass, Field(examples=[TrainClass.SLEEPER])]
    quota: Annotated[Quota, Field(default=Quota.GENERAL, examples=[Quota.GENERAL])]
    passenger_count: Annotated[int, Field(examples=["2"])]
    train_type: Annotated[str, Field(examples=["special"])]
