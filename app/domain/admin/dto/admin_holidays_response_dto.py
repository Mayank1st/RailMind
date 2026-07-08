from datetime import date, datetime

from app.schemas.base import BaseDTO


# -- HolidayItem (one calendar row) ------------------------------
class HolidayItemDTO(BaseDTO):
    festival_window_id: str
    name: str  # FESTIVAL
    festival_date: date  # DATE
    region: str  # REGION
    lookahead_days: int  # WINDOW "+Xd"
    lookbehind_days: int  # WINDOW "-Yd"
    window_total_days: int  # lookahead + lookbehind + the day itself
    demand_tier: str  # LOW | MEDIUM | HIGH | VERY_HIGH
    demand_tier_label: str  # "Very high"
    is_active: bool
    status: str  # "active" | "disabled"
    created_at: datetime
