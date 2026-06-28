from enum import Enum

# ── Error code ────────────────────────────────────────────────────────────────
ERROR_CODE_PREDICTION = "RM-WL-PRED-001"

# ── Buckets (P(WL → CNF) → human-readable band) — planning doc §2 ──────────────
# HIGH > 0.80 · MEDIUM 0.40–0.80 · LOW < 0.40.
BUCKET_HIGH_MIN = 0.80  # > this -> HIGH (relax)
BUCKET_LOW_MAX = (
    0.40  # < this -> LOW (alternate plan); == LOW boundary == ALT_THRESHOLD
)

# ── Alternatives threshold (single tunable; planning doc §3) ───────────────────
ALT_THRESHOLD = 0.40

# ── Alternatives fetch (reuses Phase-1 search; planning doc §3) ────────────────
ALT_FLEX_DAYS = 1  # same date + ±1 day
ALT_LIMIT = 5  # max alternative trains returned
ALT_SEARCH_SIZE = 25  # page size scanned from Phase-1 search before trimming

# ── Confidence threshold (response meta; planning doc §4) ──────────────────────
# Surfaced in `meta` so the client can decide how firmly to present the bucket.
CONFIDENCE_THRESHOLD = 0.75

# ── Probability bounds & precision ────────────────────────────────────────────
# Never show a flat 0.0 / 1.0 — a waitlist is never a literal certainty either way
# (honest low-confidence; planning doc §2).
MIN_PROB = 0.02
MAX_PROB = 0.95
PROB_DECIMALS = 2

# ── WL-type priors (cold-start P(WL → CNF) when live capacity is unknown) ───────
# GNWL > RLWL > PQWL > TQWL — the single richest signal (planning doc §6.2).
WL_TYPE_BASE_PROB = {
    "GNWL": 0.70,  # origin/near-origin — most seats here, highest cancellation volume
    "RLWL": 0.45,  # remote-location quota — lower volume
    "PQWL": 0.30,  # pooled quota between intermediate stations — limited pool
    "TQWL": 0.10,  # Tatkal WL — never promotes to RAC, structurally weak
    "RQWL": 0.30,  # request quota — edge cases
}
WL_TYPE_BASE_PROB_DEFAULT = 0.30

# ── WL-type multiplier (applied on the ratio-based estimate; planning doc §6.2) ─
# Same "WL 23" is safe in GNWL, weak in PQWL, near-dead in TQWL.
WL_TYPE_MULTIPLIER = {
    "GNWL": 1.00,
    "RLWL": 0.85,
    "PQWL": 0.70,
    "TQWL": 0.30,
    "RQWL": 0.70,
}
WL_TYPE_MULTIPLIER_DEFAULT = 0.70

# TQWL never reaches RAC (Phase-1 fact) — structural cap regardless of position.
TQWL_MAX_PROB = 0.20

# ── Ratio-based core (current_position vs expected cancellations) ──────────────
RATIO_CENTER = 1.0
RATIO_LOGISTIC_K = 1.8

# Typical WL clearance depth by class (seats that realistically turn over before
REFERENCE_WL_DEPTH = {
    "SL": 90,  # most coaches/seats — deepest turnover
    "2S": 80,
    "3E": 60,
    "3A": 50,
    "CC": 50,
    "2A": 30,
    "FC": 15,
    "1A": 12,  # fewest seats — shallow turnover
}
REFERENCE_WL_DEPTH_DEFAULT = 50

# ── Route/class historical cancellation rate (planning doc §6.2) ──────────────
DEFAULT_ROUTE_CANCEL_RATE = 0.25
MIN_HISTORY_FOR_CANCEL_RATE = 20

# ── Days-to-journey multiplier (more lead → more cancellation opportunity) ─────
DAYS_TOO_EARLY = 30  # > this: cancellations haven't really started yet
DAYS_PEAK_MIN = 7  # 7–14 days: peak cancellation window
DAYS_MID_MIN = 15
DAYS_NEAR = 3  # < this: chart prep imminent, little time left

MULT_DAYS_TOO_EARLY = 0.90
MULT_DAYS_MID = 1.05
MULT_DAYS_PEAK = 1.15
MULT_DAYS_NEAR = 1.08
MULT_DAYS_IMMINENT = 0.95


class PredictionStatus(str, Enum):
    WAITLISTED = "WAITLISTED"  # a prediction was produced
    NOT_WAITLISTED = "NOT_WAITLISTED"  # already CNF/RAC — no prediction needed


class PredictionBucket(str, Enum):
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"


class PredictionSource(str, Enum):
    RULES = "RULES"
    MODEL = "MODEL"


# ── Per-bucket action line (planning doc §2) ───────────────────────────────────
BUCKET_ACTION = {
    PredictionBucket.HIGH: "Relax — strong chance of confirmation.",
    PredictionBucket.MEDIUM: "Keep a backup in mind — decent chance, but no guarantee.",
    PredictionBucket.LOW: "Make an alternate plan — low chance of confirmation.",
}
