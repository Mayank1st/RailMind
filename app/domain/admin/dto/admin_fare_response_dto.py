from datetime import date, datetime

from app.schemas.base import BaseDTO


# -- FareRuleItem (one row of the fare table) --------------------
class FareRuleItemDTO(BaseDTO):
    train_class: str  # SL
    class_name: str  # Sleeper
    base_fare_per_km: float
    reservation_charge: int
    superfast_min_charge: int
    tatkal_multiplier: float
    premium_tatkal_min_multiplier: float
    premium_tatkal_max_multiplier: float
    gst_percent: float
    minimum_fare: int


# -- FareVersion (version metadata) ------------------------------
class FareVersionDTO(BaseDTO):
    version_id: str
    version_label: str
    effective_from: date
    status: str  # DRAFT | SCHEDULED | LIVE | ARCHIVED
    change_note: str | None
    published_at: datetime | None
    is_live: bool
    created_at: datetime


# -- FareRulesView (the table page: current version + its rules) -
class FareRulesViewDTO(BaseDTO):
    version: FareVersionDTO
    rules: list[FareRuleItemDTO]


# -- FarePreviewResponse (indicative banner-formula result) ------
class FarePreviewResponseDTO(BaseDTO):
    distance_km: int
    base_fare: float  # base_fare_per_km × distance
    reservation_charge: int
    superfast_charge: int
    tatkal_multiplier: float
    tatkal_applied: bool
    gst_percent: float
    gst_amount: float
    total_fare: float
