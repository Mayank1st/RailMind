from enum import Enum

ERR_AUDIT_WRITE_FAILED = "RM-ADMIN-AUDIT-001"

# Read side (Audit Log screen) — newest activity first when ?order_by= is omitted.
DEFAULT_AUDIT_LOGS_ORDER: list[str] = ["-created_at"]


class AuditTargetType(str, Enum):
    USER = "USER"
    BOOKING = "BOOKING"
    KYC = "KYC"
    JOB = "JOB"
    EMAIL = "EMAIL"
    CONFIG = "CONFIG"
    AUTH = "AUTH"
    FARE = "FARE"
    HOLIDAY = "HOLIDAY"
    RATE_LIMIT = "RATE_LIMIT"
    QUOTA = "QUOTA"
    ADVISOR = "ADVISOR"
    MODEL = "MODEL"
    TRAIN = "TRAIN"
    ROUTE = "ROUTE"
    STATION = "STATION"


class AuditAction(str, Enum):
    # ─── Admin console auth (login / logout / failed attempts) ────────────────
    ADMIN_LOGIN = "ADMIN_LOGIN"
    ADMIN_LOGOUT = "ADMIN_LOGOUT"
    ADMIN_LOGIN_FAILED = "ADMIN_LOGIN_FAILED"

    # ─── User management ──────────────────────────────────────────────────────
    USER_ROLE_CHANGED = "USER_ROLE_CHANGED"
    USER_DEACTIVATED = "USER_DEACTIVATED"
    USER_REACTIVATED = "USER_REACTIVATED"
    USER_KYC_APPROVED = "USER_KYC_APPROVED"
    USER_KYC_REJECTED = "USER_KYC_REJECTED"

    # ─── Config · Fare rules ──────────────────────────────────────────────────
    FARE_VERSION_CREATED = "FARE_VERSION_CREATED"
    FARE_RULE_EDITED = "FARE_RULE_EDITED"
    FARE_VERSION_PUBLISHED = "FARE_VERSION_PUBLISHED"

    # ─── Config · Holiday calendar ────────────────────────────────────────────
    HOLIDAY_CREATED = "HOLIDAY_CREATED"
    HOLIDAY_UPDATED = "HOLIDAY_UPDATED"
    HOLIDAY_DELETED = "HOLIDAY_DELETED"

    # ─── Config · Rate limits ─────────────────────────────────────────────────
    RATE_LIMIT_CREATED = "RATE_LIMIT_CREATED"
    RATE_LIMIT_UPDATED = "RATE_LIMIT_UPDATED"
    RATE_LIMIT_DELETED = "RATE_LIMIT_DELETED"

    # ─── Config · Quota allocation ────────────────────────────────────────────
    QUOTA_CREATED = "QUOTA_CREATED"
    QUOTA_UPDATED = "QUOTA_UPDATED"
    QUOTA_DELETED = "QUOTA_DELETED"

    # ─── AI Control · Advisor toggles ─────────────────────────────────────────
    ADVISOR_STATE_CHANGED = "ADVISOR_STATE_CHANGED"

    # ─── AI Control · Model versions ──────────────────────────────────────────
    MODEL_VERSION_ACTIVATED = "MODEL_VERSION_ACTIVATED"
    MODEL_FALLBACK_FORCED = "MODEL_FALLBACK_FORCED"

    # ─── AI Control · Retrain ─────────────────────────────────────────────────
    RETRAIN_TRIGGERED = "RETRAIN_TRIGGERED"
    MODEL_PROMOTED = "MODEL_PROMOTED"
    RETRAIN_REJECTED = "RETRAIN_REJECTED"

    # ─── Master data — Trains ─────────────────────────────────────────────────
    TRAIN_CREATED = "TRAIN_CREATED"
    TRAIN_UPDATED = "TRAIN_UPDATED"
    TRAIN_DELETED = "TRAIN_DELETED"  # soft delete (is_active → false)

    # ─── Master data — Routes ─────────────────────────────────────────────────
    ROUTE_CREATED = "ROUTE_CREATED"
    ROUTE_UPDATED = "ROUTE_UPDATED"
    ROUTE_DELETED = "ROUTE_DELETED"  # hard delete (no dependents)

    # ─── Master data — Stations ───────────────────────────────────────────────
    STATION_CREATED = "STATION_CREATED"
    STATION_UPDATED = "STATION_UPDATED"
    STATION_DELETED = "STATION_DELETED"  # soft delete (is_active → false)
