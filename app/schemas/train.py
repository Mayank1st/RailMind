from app.schemas.base import BaseDTO
from typing import Annotated, Optional
from pydantic import EmailStr, Field, field_validator, model_validator


from typing import Annotated
from pydantic import Field


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
