from typing import Optional

from app.schemas.base import BaseDTO


# -- StationBrief --------------------------------------------
class StationBriefDTO(BaseDTO):
    code: str
    name: str


# -- ClusterResponse -----------------------------------------
class ClusterResponseDTO(BaseDTO):
    station_code: str
    in_cluster: bool
    cluster_code: Optional[str] = None
    cluster_name: Optional[str] = None
    primary_station: Optional[StationBriefDTO] = None
    members: list[StationBriefDTO] = []
    also_covered: list[str] = []
