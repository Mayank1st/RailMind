from app.schemas.base import BaseDTO
from datetime import date


# -- CoachResponse -------------------------------------------
class CoachResponseDTO(BaseDTO):
    coach_number: str
    train_class: str
    total_seats: int
    is_ac: bool


# -- TrainDetailResponse -------------------------------------
class TrainDetailResponseDTO(BaseDTO):
    train_number: str
    train_name: str
    coaches: list[CoachResponseDTO]


# -- SeatResponse --------------------------------------------
class SeatResponseDTO(BaseDTO):
    seat_number: int
    berth_type: str
    is_available: bool


# -- CoachSeatAvailabilityResponse ---------------------------
class CoachSeatAvailabilityResponseDTO(BaseDTO):
    coach_number: str
    train_class: str
    total_seats: int
    available_seats: int
    coach_position: int | None
    seats: list[SeatResponseDTO]


# -- SeatAvailabilityResponse --------------------------------
class SeatAvailabilityResponseDTO(BaseDTO):
    train_number: str
    train_name: str
    journey_date: date
    from_station: str
    to_station: str
    train_class: str
    quota: str
    availability_status: str
    available_seats: int
    available_rac_slots: int
    wl_count: int
    next_wl_position: int
    wl_type: str


# -- CoachWiseSeatAvailabilityResponse -----------------------
class CoachWiseSeatAvailabilityResponseDTO(BaseDTO):
    train_number: str
    train_name: str
    journey_date: date
    from_station: str
    to_station: str
    train_class: str
    quota: str
    wl_type: str
    coaches: list[CoachSeatAvailabilityResponseDTO]
