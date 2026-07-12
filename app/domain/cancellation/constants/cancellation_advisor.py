from enum import Enum

# ── Error code ────────────────────────────────────────────────────────────────
# The advisor must never block the cancellation flow — every failure logs under
# this code and the endpoint degrades to a safe default (graceful degradation).
ERROR_CODE_ADVISOR = "RM-CNL-ADV-001"

# ── Rounding / display ────────────────────────────────────────────────────────
HOURS_DECIMALS = 1
AMOUNT_DECIMALS = 2

# ── Departure fallback ────────────────────────────────────────────────────────
# When the boarding stop has no departure_time, assume midnight of the journey
# date — that UNDERSTATES hours-to-departure, pushing the estimate into the
# harsher slab. Safe bias: never promise more refund than the user will get.
FALLBACK_DEPARTURE_HOUR = 0

# ── Refund-ladder windows ─────────────────────────────────────────────────────
# Percent slabs are flat within a window, so one representative hours-value per
# window is enough to price it. Each entry:
#   (window label, representative hours, lower-bound hours before departure)
# cancel_by for a window = departure − lower_bound (UNDER_4H is open-ended).
LADDER_WINDOWS: list[tuple[str, float, float]] = [
    ("BEFORE_48H", 49.0, 48.0),  # > 48h  -> flat cancellation charge
    ("H48_TO_12H", 13.0, 12.0),  # 48-12h -> 25% deduction (min flat)
    ("H12_TO_4H", 5.0, 4.0),  # 12-4h  -> 50% deduction (min flat)
    ("UNDER_4H", 1.0, 0.0),  # < 4h   -> no online refund
]


class AdviceStatus(str, Enum):
    ADVISED = "ADVISED"  # advice + refund preview produced
    ALREADY_CANCELLED = "ALREADY_CANCELLED"  # nothing left to advise on
    NOT_CANCELLABLE = "NOT_CANCELLABLE"  # departed / chart prepared
    NOT_APPLICABLE = "NOT_APPLICABLE"  # unpaid booking — no refund question


class AdviceRecommendation(str, Enum):
    HOLD = "HOLD"  # keep the ticket (WL likely confirms / nothing to gain)
    MONITOR = "MONITOR"  # unclear — re-check closer to journey
    CANCEL_NOW = "CANCEL_NOW"  # WL unlikely to confirm — cut losses now
    CANCEL_EARLY = "CANCEL_EARLY"  # CNF: if cancelling at all, do it before the drop


class AdviceSource(str, Enum):
    RULES = "RULES"
    MODEL = "MODEL"


# ── WL bucket → recommendation (bucket comes from the Waitlist Predictor #03) ──
WL_BUCKET_RECOMMENDATION = {
    "HIGH": AdviceRecommendation.HOLD,
    "MEDIUM": AdviceRecommendation.MONITOR,
    "LOW": AdviceRecommendation.CANCEL_NOW,
}
# When the embedded WL prediction is degraded/unavailable (no probability), never
# advise CANCEL_NOW off a failure — fall back to MONITOR.
WL_DEGRADED_RECOMMENDATION = AdviceRecommendation.MONITOR

# ── Per-recommendation action line (mirrors #03 BUCKET_ACTION) ─────────────────
RECOMMENDATION_ACTION = {
    AdviceRecommendation.HOLD: "Hold your ticket — cancelling now gains you nothing.",
    AdviceRecommendation.MONITOR: (
        "Hard to call — hold for now and re-check closer to the journey."
    ),
    AdviceRecommendation.CANCEL_NOW: (
        "Consider cancelling now — low confirmation chance, and the refund "
        "won't get better by waiting."
    ),
    AdviceRecommendation.CANCEL_EARLY: (
        "If you might cancel, do it before the deadline — the refund drops after it."
    ),
}
