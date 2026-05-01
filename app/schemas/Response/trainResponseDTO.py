from app.schemas.Response.baseResponseDTO import BaseDTO
from datetime import date


class CoachResponse(BaseDTO):
    coach_number: str
    train_class: str
    total_seats: int
    is_ac: bool


class TrainDetailResponse(BaseDTO):
    train_number: str
    train_name: str
    coaches: list[CoachResponse]


class SeatResponse(BaseDTO):
    seat_number: int
    berth_type: str
    is_available: bool


class CoachSeatAvailabilityResponse(BaseDTO):
    coach_number: str
    train_class: str
    total_seats: int
    available_seats: int
    coach_position: int | None
    seats: list[SeatResponse]


class SeatAvailabilityResponse(BaseDTO):
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


class CoachWiseSeatAvailabilityResponse(BaseDTO):
    train_number: str
    train_name: str
    journey_date: date
    from_station: str
    to_station: str
    train_class: str
    quota: str
    wl_type: str
    coaches: list[CoachSeatAvailabilityResponse]
