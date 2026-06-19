from app.schemas.base import BaseDTO
from app.core.constants.train import TrainClass, Quota
from typing import Annotated, Literal, Optional
from pydantic import EmailStr, Field, field_validator, model_validator


from typing import Annotated
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo
from pydantic import Field
from enum import Enum

from app.core.constants.booking import MAX_ADVANCE_BOOKING_DAYS


class SearchTrainDTO(BaseDTO):

    fromStationCode: Annotated[
        str,
        Field(min_length=2, max_length=5, examples=["DR"]),
    ]

    toStationCode: Optional[
        Annotated[
            str,
            Field(min_length=2, max_length=5, examples=["RNC"]),
        ]
    ] = None

    journey_date: Annotated[
        date,
        Field(
            examples=["2026-06-20"],
            description="Journey date (YYYY-MM-DD) — trains running on this date",
        ),
    ]

    @field_validator("journey_date")
    @classmethod
    def _validate_journey_date(cls, v: date) -> date:
        today = datetime.now(ZoneInfo("Asia/Kolkata")).date()
        if v < today:
            raise ValueError("journey_date cannot be in the past")
        if v > today + timedelta(days=MAX_ADVANCE_BOOKING_DAYS):
            raise ValueError(
                f"journey_date cannot be more than {MAX_ADVANCE_BOOKING_DAYS} days in advance"
            )
        return v

    train_class: Optional[
        Annotated[
            TrainClass,
            Field(examples=[TrainClass.SLEEPER]),
        ]
    ] = TrainClass.SLEEPER

    quota: Optional[
        Annotated[
            Quota,
            Field(examples=[Quota.GENERAL]),
        ]
    ] = Quota.GENERAL

    nearby_stations: Annotated[
        bool,
        Field(
            default=False,
            description="Expand source/destination to their station clusters "
            "(e.g. BCT also matches CSMT, LTT, BVI)",
        ),
    ] = False

    flexible_dates: Annotated[
        bool,
        Field(
            default=False,
            description="Also search ±flex_days around journey_date (past dropped)",
        ),
    ] = False
    flex_days: Annotated[
        int,
        Field(
            default=1,
            ge=1,
            le=3,
            description="Date flexibility window (only if flexible_dates)",
        ),
    ] = 1

    # ── Result filtering / sorting (pagination is via ?page=&size=) ──────────
    train_type: Optional[
        Annotated[
            str, Field(examples=["superfast"], description="Filter by train type")
        ]
    ] = None
    exact_only: Annotated[
        bool,
        Field(
            default=False, description="With nearby on, keep only exact src→dst matches"
        ),
    ] = False
    sort_by: Annotated[
        Literal["departure", "duration"],
        Field(default="departure", description="Result ordering"),
    ] = "departure"

    # ── Pagination (in the body) ─────────────────────────────────────────────
    page: Annotated[int, Field(default=1, ge=1, description="Page number")] = 1
    size: Annotated[
        int, Field(default=10, ge=1, le=100, description="Records per page (max 100)")
    ] = 10


class CheckSeatAvailabilityDTO(BaseDTO):
    journey_date: Annotated[date, Field(examples=["2026-05-01"])]
    from_station: Annotated[str, Field(examples=["NDLS"])]
    to_station: Annotated[str, Field(examples=["BCT"])]
    train_class: Annotated[TrainClass, Field(examples=[TrainClass.SLEEPER])]
    quota: Annotated[Quota, Field(default="GN", examples=["GN"])]
    coach_number: Optional[str] = None


class ValidateJourneyDTO(BaseDTO):
    train_number: Optional[Annotated[str, Field(examples=["12345"])]]
    from_station: Annotated[str, Field(examples=["NDLS"])]
    to_station: Annotated[str, Field(examples=["BCT"])]
