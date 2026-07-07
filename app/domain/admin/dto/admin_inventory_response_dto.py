from datetime import date

from app.schemas.base import BaseDTO


# -- AdminInventorySummary (one list row) ------------------------
class AdminInventorySummaryDTO(BaseDTO):
    train_id: str
    train_number: str | None  # TRAIN column
    train_name: str | None
    journey_date: date  # JOURNEY column
    train_class: str  # CLASS column (SL | 3A | 2A | 1A | CC | 2S | FC | 3E)
    booked_confirmed_seats: int  # BOOKED (of BOOKED / CAP) — summed over quotas
    total_confirmed_seats: int  # CAP (of BOOKED / CAP) — summed over quotas
    available_confirmed_seats: int
    available_rac_slots: int
    wl_depth: int  # WL DEPTH column — deepest quota queue (0 = none)
    is_chart_prepared: bool  # true only when every quota queue is charted
    chart_label: str  # CHART pill: "prepared" | "not prepared"
