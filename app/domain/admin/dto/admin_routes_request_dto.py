import uuid
from typing import Optional

from pydantic import Field

from app.domain.admin.constants.admin_master_data import RailwayZone
from app.schemas.base import BaseDTO


# -- AdminCreateRouteRequest -------------------------------------
class AdminCreateRouteRequestDTO(BaseDTO):
    source_station_id: uuid.UUID
    destination_station_id: uuid.UUID
    corridor_name: Optional[str] = Field(default=None, max_length=100)
    distance_km: Optional[int] = Field(default=None, ge=0)
    zones: list[RailwayZone] = Field(default_factory=list)
    trains_on_route: int = Field(default=0, ge=0, le=32767)


# -- AdminUpdateRouteRequest -------------------------------------
class AdminUpdateRouteRequestDTO(BaseDTO):
    source_station_id: Optional[uuid.UUID] = None
    destination_station_id: Optional[uuid.UUID] = None
    corridor_name: Optional[str] = Field(default=None, max_length=100)
    distance_km: Optional[int] = Field(default=None, ge=0)
    zones: Optional[list[RailwayZone]] = None
    trains_on_route: Optional[int] = Field(default=None, ge=0, le=32767)
