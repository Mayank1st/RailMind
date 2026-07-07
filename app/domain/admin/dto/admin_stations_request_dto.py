from typing import Optional

from pydantic import Field

from app.domain.admin.constants.admin_master_data import RailwayZone
from app.schemas.base import BaseDTO


# -- AdminCreateStationRequest -----------------------------------
class AdminCreateStationRequestDTO(BaseDTO):
    station_code: str = Field(min_length=1, max_length=10)
    station_name: str = Field(min_length=1, max_length=100)
    city: str = Field(min_length=1, max_length=60)
    state: Optional[str] = Field(default=None, max_length=60)
    zone: Optional[RailwayZone] = None
    platforms: Optional[int] = Field(default=None, ge=0, le=200)
    is_operational: bool = True


# -- AdminUpdateStationRequest -----------------------------------
class AdminUpdateStationRequestDTO(BaseDTO):
    station_code: Optional[str] = Field(default=None, min_length=1, max_length=10)
    station_name: Optional[str] = Field(default=None, min_length=1, max_length=100)
    city: Optional[str] = Field(default=None, min_length=1, max_length=60)
    state: Optional[str] = Field(default=None, max_length=60)
    zone: Optional[RailwayZone] = None
    platforms: Optional[int] = Field(default=None, ge=0, le=200)
    is_operational: Optional[bool] = None
