# Admin Config → Holiday Calendar (festival demand windows).
#
# CRUD over the festival_windows table. Curated config the Fare & Waitlist
# advisors can read to adjust predictions. `is_active` = the enable/disable
# toggle. The advisor-side integration (reading demand_tier into predictions) is
# a follow-up — today the fare-advisor holiday context is display-only.

from enum import Enum

# ─── Error codes (RM-ADMIN-HOL-NNN) ───────────────────────────────────────────

ERR_HOLIDAY_NOT_FOUND = "RM-ADMIN-HOL-001"


# ─── Demand tier ──────────────────────────────────────────────────────────────
class DemandTier(str, Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    VERY_HIGH = "VERY_HIGH"


DEMAND_TIER_LABELS = {
    DemandTier.LOW.value: "Low",
    DemandTier.MEDIUM.value: "Medium",
    DemandTier.HIGH.value: "High",
    DemandTier.VERY_HIGH.value: "Very high",
}

# ─── Status labels (is_active → UI) ───────────────────────────────────────────

STATUS_ACTIVE = "active"
STATUS_DISABLED = "disabled"

# Newest-festival-first is odd for a calendar; default to chronological.
DEFAULT_HOLIDAYS_ORDER = "festival_date"
