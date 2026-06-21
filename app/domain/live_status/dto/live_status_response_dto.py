from datetime import date, datetime
from typing import Optional

from app.schemas.base import BaseDTO


# -- StationProgress -----------------------------------------
class StationProgressDTO(BaseDTO):
    station_code: str
    station_name: str
    sequence_number: int
    scheduled_arrival: Optional[str] = None
    actual_arrival: Optional[str] = None
    scheduled_departure: Optional[str] = None
    actual_departure: Optional[str] = None
    arrival_delay_minutes: int = 0
    departure_delay_minutes: int = 0
    distance_km: Optional[float] = None
    halt_minutes: Optional[int] = None
    platform_number: Optional[str] = None
    day_number: Optional[int] = None
    is_departed: bool = False
    is_current: bool = False


# -- LiveStatusResponse --------------------------------------
class LiveStatusResponseDTO(BaseDTO):
    train_number: str
    train_name: str
    journey_date: date
    current_station_code: Optional[str] = None
    current_station_name: Optional[str] = None
    current_delay_minutes: int = 0
    last_reported_at: Optional[str] = None
    expected_platform: Optional[str] = None
    route: list[StationProgressDTO] = []
    is_stale: bool = False
    source: str
    fetched_at: datetime
