from app.schemas.base import BaseDTO


# -- StationRef (nested — shared by trains & routes responses) ----
class StationRefDTO(BaseDTO):
    station_id: str
    station_code: str
    station_name: str
    city: str | None


# -- AdminStationSummary (list row + edit drawer) ----------------
class AdminStationSummaryDTO(BaseDTO):
    station_id: str
    station_code: str  # CODE
    station_name: str  # STATION
    city: str  # CITY
    state: str | None
    zone: str | None  # ZONE
    platforms: int | None  # PLATFORMS
    is_operational: bool  # "Station operational" toggle
    is_active: bool  # false = soft-deleted (hidden from default list)
