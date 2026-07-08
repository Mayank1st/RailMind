from enum import Enum

# ─── Error codes (RM-ADMIN-RL-NNN) ────────────────────────────────────────────

ERR_RATE_LIMIT_NOT_FOUND = "RM-ADMIN-RL-001"
ERR_RATE_LIMIT_DUPLICATE = "RM-ADMIN-RL-002"


# ─── Scope (which Redis counter subject the limiter buckets by) ───────────────
class RateLimitScope(str, Enum):
    PER_USER = "PER_USER"
    PER_IP = "PER_IP"
    GLOBAL = "GLOBAL"


SCOPE_LABELS = {
    RateLimitScope.PER_USER.value: "per user",
    RateLimitScope.PER_IP.value: "per IP",
    RateLimitScope.GLOBAL.value: "global",
}

# ─── Status (derived from CURRENT PEAK / limit) ───────────────────────────────
# "near" once usage crosses this fraction of the limit; "at cap" once it meets it.
NEAR_RATIO = 0.8

STATUS_OK = "ok"
STATUS_NEAR = "near"
STATUS_AT_CAP = "at cap"

# Requests beyond the limit return this (surfaced in the FE info banner).
RATE_LIMIT_REJECT_STATUS = 429
