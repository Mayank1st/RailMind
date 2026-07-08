from datetime import date
from typing import Optional

from pydantic import Field

from app.domain.admin.constants.admin_holidays import DemandTier
from app.schemas.base import BaseDTO


# -- CreateHolidayRequest ----------------------------------------
class CreateHolidayRequestDTO(BaseDTO):
    name: str = Field(min_length=1, max_length=100)
    festival_date: date
    region: str = Field(min_length=1, max_length=60)
    lookahead_days: int = Field(ge=0, le=60)
    lookbehind_days: int = Field(ge=0, le=60)
    demand_tier: DemandTier
    is_active: bool = True


# -- UpdateHolidayRequest (partial edit + enable/disable) --------
class UpdateHolidayRequestDTO(BaseDTO):
    name: Optional[str] = Field(default=None, min_length=1, max_length=100)
    festival_date: Optional[date] = None
    region: Optional[str] = Field(default=None, min_length=1, max_length=60)
    lookahead_days: Optional[int] = Field(default=None, ge=0, le=60)
    lookbehind_days: Optional[int] = Field(default=None, ge=0, le=60)
    demand_tier: Optional[DemandTier] = None
    is_active: Optional[bool] = None  # the Disable/Enable buttons
