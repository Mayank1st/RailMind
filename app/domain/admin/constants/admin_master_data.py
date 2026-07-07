from enum import Enum

# ─── Error codes (RM-ADMIN-MD-NNN) ────────────────────────────────────────────

ERR_TRAIN_NOT_FOUND = "RM-ADMIN-MD-001"
ERR_STATION_NOT_FOUND = "RM-ADMIN-MD-002"
ERR_ROUTE_NOT_FOUND = "RM-ADMIN-MD-003"
ERR_TRAIN_NUMBER_TAKEN = "RM-ADMIN-MD-004"
ERR_STATION_CODE_TAKEN = "RM-ADMIN-MD-005"
ERR_ROUTE_DUPLICATE = "RM-ADMIN-MD-006"
ERR_STATION_REF_INVALID = "RM-ADMIN-MD-007"  # source/destination station missing
ERR_SAME_SOURCE_DEST = "RM-ADMIN-MD-008"
ERR_NO_CHANGES = "RM-ADMIN-MD-009"


# ─── Railway zones (station zone + route zones dropdown) ──────────────────────
class RailwayZone(str, Enum):
    WR = "WR"
    NR = "NR"
    ER = "ER"
    SR = "SR"
    CR = "CR"
    ECR = "ECR"
    SWR = "SWR"
    NER = "NER"
    SER = "SER"
    NCR = "NCR"


# ─── Days of operation (trains.runs_on_days) — lowercase 3-letter codes ────────
class DayOfWeek(str, Enum):
    MON = "mon"
    TUE = "tue"
    WED = "wed"
    THU = "thu"
    FRI = "fri"
    SAT = "sat"
    SUN = "sun"


# ─── Train status labels (is_paused → UI) ─────────────────────────────────────
TRAIN_STATUS_ACTIVE = "active"
TRAIN_STATUS_PAUSED = "paused"
