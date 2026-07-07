from datetime import datetime

from app.schemas.base import BaseDTO


# -- Metric KPI --------------------------------------------------
class MetricKpiDTO(BaseDTO):
    value: float
    delta_pct: (
        float | None
    )  # vs the preceding equal-length window; None when no prior data
    spark: list[float]  # per-bucket series driving the tile sparkline


# -- Bookings Volume Point ---------------------------------------
class BookingsVolumePointDTO(BaseDTO):
    bucket: str  # ISO-8601 IST bucket start (hourly for 24h, daily otherwise)
    confirmed: int  # CONFIRMED + RAC
    waitlist: int  # WAITLISTED


# -- Revenue By Class --------------------------------------------
class RevenueByClassDTO(BaseDTO):
    train_class: str  # SL / 3A / 2A / 1A / CC / ...
    revenue: float
    share_pct: float  # share of window revenue, 0-100


# -- Top Route ---------------------------------------------------
class TopRouteDTO(BaseDTO):
    source_code: str
    source_city: str
    destination_code: str
    destination_city: str
    trains_count: int  # distinct trains serving the corridor in-window
    bookings: int
    occupancy_pct: float  # weighted over the corridor's inventories, 0-100
    wl_depth: int  # deepest current waitlist across those inventories
    revenue: float


# -- Overview Metrics --------------------------------------------
class OverviewMetricsResponseDTO(BaseDTO):
    range: str  # echo of the selected window (24h / 7d / 30d)
    generated_at: datetime
    bookings_per_day: MetricKpiDTO
    revenue: MetricKpiDTO
    seat_occupancy: MetricKpiDTO
    cancellation_rate: MetricKpiDTO
    bookings_volume: list[BookingsVolumePointDTO]
    revenue_by_class: list[RevenueByClassDTO]
    top_routes: list[TopRouteDTO]
