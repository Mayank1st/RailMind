from enum import Enum


class ChartStatus(str, Enum):
    NOT_PREPARED = "NOT_PREPARED"
    STAGE_1_PREPARED = "STAGE_1_PREPARED"
    FINAL_PREPARED = "FINAL_PREPARED"


# ── Trigger windows (hours before scheduled departure) ────────────────────────
CHART_STAGE_1_WINDOW_MIN_HOURS = 7
CHART_STAGE_1_WINDOW_MAX_HOURS = 8

CHART_STAGE_2_WINDOW_MIN_HOURS = 3
CHART_STAGE_2_WINDOW_MAX_HOURS = 4

# ── Discovery cron cadence ────────────────────────────────────────────────────
CHART_CHECK_INTERVAL_MINUTES = 5

# ── Mock clerkage (₹) for auto-cancelled WL ───────────────────────────────────
CHART_AUTO_CANCEL_CLERKAGE = {
    "SL": 60,
    "3A": 65,
    "2A": 65,
    "1A": 65,
    "CC": 60,
    "2S": 30,
    "FC": 65,
    "3E": 60,
}
