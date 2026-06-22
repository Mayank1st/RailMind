"""Leakage-free feature engineering for the Level-2 autofill class model.

Imported by BOTH the offline trainer (scripts/phase-2/train_autofill_class.py) and
the online inference pipeline (autofill_class.py) so the exact same encoding runs in
training and serving. No leakage features (fare / booking_status / pnr / post-booking
status) are produced here.
"""

from __future__ import annotations

from app.domain.autofill.constants.autofill import DistanceBucket, bucket_for_distance

MODEL_VERSION = "autofill-class-v2"

# ── Label space (fixed order -> integer code) ─────────────────────────────────
CLASS_ORDER = ["3A", "SL", "2S", "2A", "CC", "1A"]
CLASS_TO_IDX = {c: i for i, c in enumerate(CLASS_ORDER)}
IDX_TO_CLASS = {i: c for i, c in enumerate(CLASS_ORDER)}

# ── Historical-class feature: an extra NONE token for "no prior history" ───────
HIST_NONE = "NONE"
HIST_CLASS_ORDER = [HIST_NONE, *CLASS_ORDER]  # NONE=0, classes 1..6
HIST_CLASS_TO_CODE = {c: i for i, c in enumerate(HIST_CLASS_ORDER)}

BUCKET_TO_CODE = {
    DistanceBucket.SHORT.value: 0,
    DistanceBucket.MEDIUM.value: 1,
    DistanceBucket.LONG.value: 2,
    DistanceBucket.XLONG.value: 3,
}

# ── Time / season helpers ─────────────────────────────────────────────────────
FESTIVAL_MONTHS = {3, 10, 11}
DAY_START_HOUR = 6
NIGHT_START_HOUR = 18

# Recency-weighted history: mode over the user's last N bookings (captures taste
# shifts a cumulative mode would miss — e.g. persona #18 Recency Shifter).
RECENCY_WINDOW = 20

# Nearby-distance history: mode over the user's prior bookings within +/- this many
# km of the current journey. Finer than distance_bucket, so it resolves a user's
# class boundary that sits *inside* a coarse bucket (e.g. AC user flips 3A->2A at
# ~1500km, which the LONG bucket alone hides). v2 feature.
DISTANCE_WINDOW_KM = 250

# ── Ordered feature vector fed to XGBoost ─────────────────────────────────────
FEATURE_ORDER = [
    "distance_km",
    "distance_bucket_code",
    "is_night_train",
    "passenger_count",
    "has_senior",
    "has_child",
    "is_weekend",
    "month",
    "is_festival_season",
    "quota_code",
    "user_hist_top_class_code",
    "user_hist_class_for_bucket_code",
    "user_hist_recent_class_code",
    "user_hist_class_for_distance_code",
]


def hour_is_night(hour: int) -> bool:
    return hour < DAY_START_HOUR or hour >= NIGHT_START_HOUR


def departure_hour(departure_time: object) -> int:
    """'HH:MM:SS' -> hour int; defaults to 12 (day) when unparsable."""
    try:
        return int(str(departure_time)[:2])
    except (ValueError, TypeError):
        return 12


def is_festival_month(month: int) -> bool:
    return month in FESTIVAL_MONTHS


def bucket_value_for_km(distance_km: int) -> str:
    return bucket_for_distance(distance_km).value


def build_quota_codes(quotas: list[str]) -> dict[str, int]:
    """Deterministic quota -> code map. 0 is reserved for quotas unseen at train
    time (so inference never crashes on a new quota)."""
    return {q: i + 1 for i, q in enumerate(sorted(set(quotas)))}


def encode_row(raw: dict, encoders: dict) -> list[float]:
    """Turn a raw feature dict into the ordered numeric vector. `raw` keys:
    distance_km, distance_bucket, is_night_train, passenger_count, has_senior,
    has_child, is_weekend, month, is_festival_season, quota,
    user_hist_top_class, user_hist_class_for_bucket."""
    quota_codes = encoders["quota_codes"]
    return [
        float(raw["distance_km"]),
        float(BUCKET_TO_CODE.get(raw["distance_bucket"], 0)),
        float(1 if raw["is_night_train"] else 0),
        float(raw["passenger_count"]),
        float(1 if raw["has_senior"] else 0),
        float(1 if raw["has_child"] else 0),
        float(1 if raw["is_weekend"] else 0),
        float(raw["month"]),
        float(1 if raw["is_festival_season"] else 0),
        float(quota_codes.get(raw["quota"], 0)),
        float(HIST_CLASS_TO_CODE.get(raw["user_hist_top_class"], 0)),
        float(HIST_CLASS_TO_CODE.get(raw["user_hist_class_for_bucket"], 0)),
        float(HIST_CLASS_TO_CODE.get(raw["user_hist_recent_class"], 0)),
        float(HIST_CLASS_TO_CODE.get(raw["user_hist_class_for_distance"], 0)),
    ]
