import uuid
from datetime import date, datetime
from typing import Optional

from app.schemas.base import BaseDTO


# -- StationBrief --------------------------------------------
class StationBriefDTO(BaseDTO):
    code: str
    name: str


# -- RecentSearch --------------------------------------------
class RecentSearchDTO(BaseDTO):
    id: uuid.UUID
    source: StationBriefDTO
    destination: StationBriefDTO
    journey_date: Optional[date] = None
    train_class: Optional[str] = None
    quota: Optional[str] = None
    searched_at: datetime
