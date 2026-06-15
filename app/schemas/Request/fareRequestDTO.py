from datetime import date
from typing import Annotated, Optional

from pydantic import Field

from app.core.constants.train import Quota, TrainClass
from app.schemas.base import BaseDTO


class FareEnquiryRequestDTO(BaseDTO):
    train_number: Annotated[str, Field(min_length=4, max_length=6, examples=["12951"])]
    source_station_code: Annotated[
        str, Field(min_length=2, max_length=10, examples=["BCT"])
    ]
    destination_station_code: Annotated[
        str, Field(min_length=2, max_length=10, examples=["NDLS"])
    ]
    journey_date: Annotated[date, Field(examples=["2026-07-15"])]
    quota: Quota = Quota.GENERAL
    train_class: Optional[TrainClass] = None
    passenger_age: Optional[int] = Field(default=None, ge=0, le=120)
    passenger_gender: Optional[str] = None
    # NOTE: source == destination is enforced in FareEnquiryService (RM-FARE-002),
    # not via a model_validator — a cross-field validator raised inside a
    # Depends()-built query model leaks as an unhandled 500 instead of a 422.


class FareBreakdownDTO(BaseDTO):
    train_class: TrainClass
    base_fare: float  # gross — before telescopic rebate
    telescopic_discount: float
    superfast_charge: float
    reservation_charge: float
    tatkal_premium: float
    concession_amount: float
    subtotal: float  # base − discount + surcharges − concession
    gst: float
    service_charge: float  # IRCTC online service charge (incl. its GST)
    total_fare: float


class FareEnquiryResponseDTO(BaseDTO):
    train_number: str
    train_name: str
    source: dict  # {code, name}
    destination: dict  # {code, name}
    journey_date: date
    distance_km: int
    quota: Quota
    fares: list[FareBreakdownDTO]
