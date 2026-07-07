from app.domain.admin.dto.admin_stations_response_dto import StationRefDTO
from app.schemas.base import BaseDTO


# -- AdminRouteSummary (list row + edit drawer) ------------------
class AdminRouteSummaryDTO(BaseDTO):
    route_id: str
    source_station: StationRefDTO  # ROUTE (source)
    destination_station: StationRefDTO  # ROUTE (destination)
    corridor_name: str | None  # CORRIDOR
    distance_km: int | None  # DISTANCE
    zones: list[str]  # ZONES
    trains_on_route: int  # TRAINS
    is_active: bool
