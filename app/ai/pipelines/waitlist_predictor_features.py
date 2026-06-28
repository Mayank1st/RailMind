from __future__ import annotations

MODEL_VERSION = "waitlist-predictor-v1"

# ── Seasonality ───────────────────────────────────────────────────────────────
FESTIVAL_MONTHS = {3, 10, 11}

# ── Distance buckets (km) — 0..3 ──────────────────────────────────────────────
SHORT_MAX_KM = 400
MEDIUM_MAX_KM = 1000
LONG_MAX_KM = 1500

# ── Categorical code maps (fixed -> train/serve parity; 0 = unseen) ───────────
TRAIN_TYPE_ORDER = [
    "EXPRESS",
    "SUPERFAST",
    "RAJDHANI",
    "SHATABDI",
    "JAN_SHATABDI",
    "DURONTO",
    "GARIB_RATH",
    "PASSENGER",
    "SUBURBAN",
    "DEMU",
    "SPECIAL",
    "HERITAGE",
    "UNKNOWN",
]
QUOTA_ORDER = ["GN", "TQ", "PT", "LD", "SS", "HP", "DF", "FT", "LB"]
CLASS_ORDER = ["SL", "3A", "2A", "1A", "CC", "2S", "FC", "3E"]
# WL type carries the strongest signal — GNWL > RLWL > PQWL > TQWL (planning §6.2).
WL_TYPE_ORDER = ["GNWL", "RLWL", "PQWL", "TQWL", "RQWL"]

TRAIN_TYPE_TO_CODE = {t: i + 1 for i, t in enumerate(TRAIN_TYPE_ORDER)}
QUOTA_TO_CODE = {q: i + 1 for i, q in enumerate(QUOTA_ORDER)}
CLASS_TO_CODE = {c: i + 1 for i, c in enumerate(CLASS_ORDER)}
WL_TYPE_TO_CODE = {w: i + 1 for i, w in enumerate(WL_TYPE_ORDER)}

# ── Ordered feature vector fed to XGBoost ─────────────────────────────────────
FEATURE_ORDER = [
    "wl_position",  # train: booking_position · serve: current_position
    "wl_type_code",  # GNWL/RLWL/PQWL/TQWL/RQWL — richest signal
    "days_to_journey",  # train: booking lead · serve: days remaining
    "train_class_code",
    "quota_code",
    "train_type_code",
    "distance_bucket_code",
    "route_cancel_rate",  # historical cancel rate for the train+class
    "month",
    "is_weekend",
    "is_festival_season",
]


def bucket_code_for_km(distance_km: int) -> int:
    if distance_km < SHORT_MAX_KM:
        return 0
    if distance_km <= MEDIUM_MAX_KM:
        return 1
    if distance_km <= LONG_MAX_KM:
        return 2
    return 3


def is_festival_month(month: int) -> bool:
    return month in FESTIVAL_MONTHS


def encode_row(raw: dict) -> list[float]:
    return [
        float(raw["wl_position"]),
        float(WL_TYPE_TO_CODE.get(raw["wl_type"], 0)),
        float(raw["days_to_journey"]),
        float(CLASS_TO_CODE.get(raw["train_class"], 0)),
        float(QUOTA_TO_CODE.get(raw["quota"], 0)),
        float(TRAIN_TYPE_TO_CODE.get(raw["train_type"], 0)),
        float(bucket_code_for_km(int(raw["distance_km"]))),
        float(raw["route_cancel_rate"]),
        float(raw["month"]),
        float(1 if raw["is_weekend"] else 0),
        float(1 if raw["is_festival_season"] else 0),
    ]
