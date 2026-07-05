from enum import Enum

from app.domain.booking.constants.booking import (
    BookingStatus,
    CANCELLED_BOOKING_STATUSES,
)

# ─── Overview dashboard config ────────────────────────────────────────────────

# All time-bucketing is done in IST so "per day" aligns with Indian rail ops.
IST_TIMEZONE_NAME = "Asia/Kolkata"

ERR_INVALID_METRICS_RANGE = "RM-ADMIN-DASH-001"

# Overview is read-heavy and tolerates minutes of staleness, so the whole
# response is cached in Redis per range. Occupancy alone scans a 16M-row table,
# so serving warm from cache is what keeps the endpoint in the ms range.
OVERVIEW_CACHE_KEY_PREFIX = "admin:metrics:overview:"
OVERVIEW_CACHE_TTL_SECONDS = 120

# Occupancy sums a multi-million-row table, so it's precomputed into the
# daily_seat_occupancies rollup by a celery-beat task at this cadence (minutes).
# A few minutes of occupancy staleness is fine for a dashboard.
OCCUPANCY_ROLLUP_REFRESH_MINUTES = 10

# Top-routes table size (matches the Overview mock — the 5 busiest corridors).
TOP_ROUTES_LIMIT = 5

# Bookings that never completed payment — excluded from every booking count so
# abandoned carts don't inflate volume / cancellation-rate metrics.
EXCLUDED_BOOKING_STATUSES: tuple[str, ...] = (
    BookingStatus.INITIATED.value,
    BookingStatus.PAYMENT_PENDING.value,
)

# The "Confirmed" series of the bookings-volume chart folds RAC into confirmed —
# an RAC passenger is boarding, so it reads as a confirmed reservation.
CONFIRMED_BOOKING_STATUSES: tuple[str, ...] = (
    BookingStatus.CONFIRMED.value,
    BookingStatus.RAC.value,
)

WAITLISTED_BOOKING_STATUS = BookingStatus.WAITLISTED.value

# Re-exported so the service imports the cancelled set from one dashboard module.
CANCELLED_STATUSES: tuple[str, ...] = tuple(CANCELLED_BOOKING_STATUSES)


class MetricsRange(str, Enum):
    """Overview time-window selector. Values are the FE toggle labels and are
    request-only (never persisted), so they stay lowercase by design."""

    LAST_24H = "24h"  # naming: ignore
    LAST_7D = "7d"  # naming: ignore
    LAST_30D = "30d"  # naming: ignore


# range → (bucket_kind, bucket_count, per-day divisor for the "/day" KPIs).
# 24h buckets hourly and counts as one day; 7d/30d bucket by calendar day.
RANGE_BUCKETS: dict[str, tuple[str, int, int]] = {
    MetricsRange.LAST_24H.value: ("hour", 24, 1),
    MetricsRange.LAST_7D.value: ("day", 7, 7),
    MetricsRange.LAST_30D.value: ("day", 30, 30),
}
