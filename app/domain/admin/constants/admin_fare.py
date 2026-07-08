from enum import Enum

# ─── Error codes (RM-ADMIN-FARE-NNN) ──────────────────────────────────────────

ERR_FARE_VERSION_NOT_FOUND = "RM-ADMIN-FARE-001"
ERR_FARE_VERSION_NOT_DRAFT = "RM-ADMIN-FARE-002"  # can only edit/publish a draft
ERR_FARE_CLASS_NOT_FOUND = "RM-ADMIN-FARE-003"  # class not in this version
ERR_FARE_NO_LIVE_VERSION = "RM-ADMIN-FARE-004"
ERR_FARE_ALREADY_PUBLISHED = "RM-ADMIN-FARE-005"


# ─── Version status ───────────────────────────────────────────────────────────
class FareVersionStatus(str, Enum):
    DRAFT = "DRAFT"  # being edited; not applied
    SCHEDULED = "SCHEDULED"  # published with a future effective_from
    LIVE = "LIVE"  # currently applied to fare_rules
    ARCHIVED = "ARCHIVED"  # a superseded past-live version


# ─── Class display names (for the table's "CLASS" column) ─────────────────────
CLASS_DISPLAY_NAMES = {
    "SL": "Sleeper",
    "3A": "AC 3-Tier",
    "2A": "AC 2-Tier",
    "1A": "First AC",
    "CC": "Chair Car",
    "2S": "Second Sitting",
    "FC": "First Class",
    "3E": "AC 3 Economy",
}

# ─── Live fare preview ────────────────────────────────────────────────────────
# Simple indicative formula shown in the drawer (NOT the production calculator):
#   ((base/km × distance) + reservation + superfast) × tatkal, then + GST.
PREVIEW_DEFAULT_DISTANCE_KM = 1373

# ─── Seed label for the initial version snapshotted from live fare_rules ───────
INITIAL_VERSION_LABEL = "v1"
