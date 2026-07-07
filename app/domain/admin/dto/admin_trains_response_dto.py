from app.domain.admin.dto.admin_stations_response_dto import StationRefDTO
from app.schemas.base import BaseDTO


# -- AdminTrainSummary (list row + edit drawer) ------------------
class AdminTrainSummaryDTO(BaseDTO):
    train_id: str
    train_number: str  # NUMBER
    train_name: str  # NAME
    source_station: StationRefDTO  # ROUTE (source)
    destination_station: StationRefDTO  # ROUTE (destination)
    train_type: str  # TYPE
    classes_offered: list[str]  # CLASSES
    runs_on_days: list[str]  # RUNS (day codes)
    distance_km: int | None
    halts: int
    pantry_car: bool
    is_paused: bool
    status: str  # STATUS — "active" | "paused"
    is_active: bool  # false = soft-deleted (hidden from default list)
