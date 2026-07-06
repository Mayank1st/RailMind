# Admin audit log — cross-cutting foundation (plan §4.3, north-star #1).
#
# Every sensitive admin action writes an admin_audit_logs row in the SAME
# transaction as the action itself (so an action can never commit without its
# audit trail). Written via AdminAuditService.record; read by the future Audit
# Log screen. Actions across the whole panel reuse these action names.

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
    MODEL = "MODEL"


class AuditAction(str, Enum):
    # ─── User management ──────────────────────────────────────────────────────
    USER_ROLE_CHANGED = "USER_ROLE_CHANGED"
    USER_DEACTIVATED = "USER_DEACTIVATED"
    USER_REACTIVATED = "USER_REACTIVATED"
    USER_KYC_APPROVED = "USER_KYC_APPROVED"
    USER_KYC_REJECTED = "USER_KYC_REJECTED"
