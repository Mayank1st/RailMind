import uuid
from datetime import date
from typing import Optional

from pydantic import Field

from app.schemas.base import BaseDTO


# -- FareRuleFields (shared editable fields) ---------------------
class _FareRuleFieldsDTO(BaseDTO):
    base_fare_per_km: Optional[float] = Field(default=None, gt=0)
    reservation_charge: Optional[int] = Field(default=None, ge=0)
    superfast_min_charge: Optional[int] = Field(default=None, ge=0)
    tatkal_multiplier: Optional[float] = Field(default=None, ge=1, le=5)
    gst_percent: Optional[float] = Field(default=None, ge=0, le=100)
    premium_tatkal_min_multiplier: Optional[float] = Field(default=None, ge=1, le=5)
    premium_tatkal_max_multiplier: Optional[float] = Field(default=None, ge=1, le=5)
    minimum_fare: Optional[int] = Field(default=None, ge=0)


# -- EditFareRuleRequest (edit one class in a DRAFT version) -----
class EditFareRuleRequestDTO(_FareRuleFieldsDTO):
    pass


# -- QuickEditFareRuleRequest (live view "Save & version") -------
class QuickEditFareRuleRequestDTO(_FareRuleFieldsDTO):
    change_note: str = Field(min_length=1, max_length=500)


# -- NewFareVersionRequest --------------------------------------
class NewFareVersionRequestDTO(BaseDTO):
    version_label: str = Field(min_length=1, max_length=50)
    effective_from: date
    clone_from_version_id: Optional[uuid.UUID] = None  # default = current live
    change_note: str = Field(min_length=1, max_length=500)


# -- FarePreviewRequest (indicative banner-formula preview) ------
class FarePreviewRequestDTO(BaseDTO):
    base_fare_per_km: float = Field(gt=0)
    reservation_charge: int = Field(ge=0)
    superfast_min_charge: int = Field(ge=0)
    tatkal_multiplier: float = Field(ge=1, le=5)
    gst_percent: float = Field(ge=0, le=100)
    distance_km: int = Field(gt=0, le=5000)
    is_tatkal: bool = False
