from app.schemas.base import BaseDTO
from app.core.constants.train import TrainClass, Quota
from typing import Annotated, Optional
from pydantic import EmailStr, Field, field_validator, model_validator


from typing import Annotated
from datetime import date
from pydantic import Field
from enum import Enum


class SearchTrainDTO(BaseDTO):

    fromStationCode: Annotated[
        str,
        Field(min_length=3, max_length=5, examples=["DR"]),
    ]

    toStationCode: Optional[
        Annotated[
            str,
            Field(min_length=3, max_length=5, examples=["RNC"]),
        ]
    ] = None

    hours: Annotated[
        int,
        Field(
            ge=1,
            le=8,
            examples=[2],
            default=1,
            description="Show trains departing/arriving in next X hours",
        ),
    ]


class CheckSeatAvailabilityDTO(BaseDTO):
    journey_date: Annotated[date, Field(examples=["2026-05-01"])]
    from_station: Annotated[str, Field(examples=["NDLS"])]
    to_station: Annotated[str, Field(examples=["BCT"])]
    train_class: Annotated[TrainClass, Field(examples=[TrainClass.SLEEPER])]
    quota: Annotated[Quota, Field(default="GN", examples=["GN"])]
    coach_number: str
