import uuid
from typing import Optional

from pydantic import Field

from app.domain.admin.constants.admin_master_data import DayOfWeek
from app.domain.train.constants.train import TrainClass, TrainType
from app.schemas.base import BaseDTO


# -- AdminCreateTrainRequest -------------------------------------
class AdminCreateTrainRequestDTO(BaseDTO):
    train_number: str = Field(min_length=1, max_length=10)
    train_name: str = Field(min_length=1, max_length=100)
    source_station_id: uuid.UUID
    destination_station_id: uuid.UUID
    train_type: TrainType = TrainType.UNKNOWN
    classes_offered: list[TrainClass] = Field(default_factory=list)
    runs_on_days: list[DayOfWeek] = Field(default_factory=list)
    distance_km: Optional[int] = Field(default=None, ge=0)
    halts: int = Field(default=0, ge=0, le=32767)
    pantry_car: bool = False
    is_paused: bool = False  # false = Active, true = Paused


# -- AdminUpdateTrainRequest -------------------------------------
class AdminUpdateTrainRequestDTO(BaseDTO):
    train_number: Optional[str] = Field(default=None, min_length=1, max_length=10)
    train_name: Optional[str] = Field(default=None, min_length=1, max_length=100)
    source_station_id: Optional[uuid.UUID] = None
    destination_station_id: Optional[uuid.UUID] = None
    train_type: Optional[TrainType] = None
    classes_offered: Optional[list[TrainClass]] = None
    runs_on_days: Optional[list[DayOfWeek]] = None
    distance_km: Optional[int] = Field(default=None, ge=0)
    halts: Optional[int] = Field(default=None, ge=0, le=32767)
    pantry_car: Optional[bool] = None
    is_paused: Optional[bool] = None
