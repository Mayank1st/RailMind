from enum import Enum

# ─── Error codes ──────────────────────────────────────────────────────────────
ADMIN_ERROR_PREFIX = "RM-ADMIN"
ERR_SEED_PROD_BLOCKED = "RM-ADMIN-SEED-001"


# ─── AI control enums (Tier 2) ────────────────────────────────────────────────
class AdvisorType(str, Enum):
    WAITLIST = "WAITLIST"
    FARE = "FARE"
    AUTOFILL = "AUTOFILL"


class FeatureFlagValue(str, Enum):
    OFF = "OFF"  # advisor disabled — endpoints return graceful "unavailable"
    FORCE_L1 = "FORCE_L1"  # skip ML model, always use rules fallback
    ON = "ON"  # normal operation (model when available, else fallback)


class LlmProvider(str, Enum):
    GEMINI = "GEMINI"
    REPLICATE = "REPLICATE"


# ─── Ops log enums (Tier 1) ───────────────────────────────────────────────────
class EmailLogStatus(str, Enum):
    QUEUED = "QUEUED"
    SENT = "SENT"
    FAILED = "FAILED"
    BOUNCED = "BOUNCED"


class JobRunStatus(str, Enum):
    RUNNING = "RUNNING"
    SUCCESS = "SUCCESS"
    FAILED = "FAILED"


class JobTriggerSource(str, Enum):
    BEAT = "BEAT"  # fired by Celery beat schedule
    MANUAL = "MANUAL"  # re-triggered by an admin from the panel
    EVENT = "EVENT"  # enqueued by an app event (e.g. booking created)
