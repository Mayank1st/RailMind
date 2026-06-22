from enum import Enum

# ── Cold-start guard ──────────────────────────────────────────────────────────
# At or below this many bookings, history is not trustworthy -> serve defaults.
COLD_START_MAX_BOOKINGS = 5

# ── Level-2 routing ───────────────────────────────────────────────────────────
# Above this many bookings, the user's history is rich enough to trust the global
# XGBoost model; at or below it, stay on Level-1 rules.
MODEL_MIN_BOOKINGS = 10

# ── Defaults (served on cold start / no usable history) ───────────────────────
DEFAULT_TRAIN_CLASS = "3A"
DEFAULT_QUOTA = "GN"
DEFAULT_BERTH = "LB"
DEFAULT_CONFIDENCE = 0.0  # defaults carry no statistical confidence

# ── Suggestion tuning ─────────────────────────────────────────────────────────
PASSENGER_SUGGESTION_LIMIT = 4
CONFIDENCE_DECIMALS = 2

# ── Distance buckets (km) ─────────────────────────────────────────────────────
# LONG is split at 1500 (LONG vs XLONG): common AC class boundaries (e.g. 3A->2A)
# sit inside a single 1000+ bucket, which a coarse bucket would hide.
SHORT_MAX_KM = 400  # short: < 400
MEDIUM_MAX_KM = 1000  # medium: 400 .. 1000 (inclusive)
LONG_MAX_KM = 1500  # long: 1000 .. 1500; xlong: > 1500


class DistanceBucket(str, Enum):
    SHORT = "SHORT"
    MEDIUM = "MEDIUM"
    LONG = "LONG"
    XLONG = "XLONG"


class AutofillSource(str, Enum):
    HISTORY = "HISTORY"
    DEFAULTS = "DEFAULTS"
    MODEL = "MODEL"


def bucket_for_distance(distance_km: int) -> DistanceBucket:
    if distance_km < SHORT_MAX_KM:
        return DistanceBucket.SHORT
    if distance_km <= MEDIUM_MAX_KM:
        return DistanceBucket.MEDIUM
    if distance_km <= LONG_MAX_KM:
        return DistanceBucket.LONG
    return DistanceBucket.XLONG


def bucket_bounds(bucket: DistanceBucket) -> tuple[int, int]:
    """Returns (low_inclusive, high_exclusive) km bounds for a bucket."""
    if bucket is DistanceBucket.SHORT:
        return (0, SHORT_MAX_KM)
    if bucket is DistanceBucket.MEDIUM:
        return (SHORT_MAX_KM, MEDIUM_MAX_KM + 1)
    if bucket is DistanceBucket.LONG:
        return (MEDIUM_MAX_KM + 1, LONG_MAX_KM + 1)
    return (LONG_MAX_KM + 1, 1_000_000)
