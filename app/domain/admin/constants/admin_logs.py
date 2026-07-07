# Admin Logs — Tier-1 observability (email logs; job/error logs land here later).
#
# Email logs are PRODUCED by app/integrations/email.py (every send is persisted
# to the email_logs table) and CONSUMED read-only by the admin console, plus a
# super-admin-only retry action.

from enum import Enum

# EmailLogStatus (QUEUED/SENT/FAILED/BOUNCED) lives in constants/admin.py and is
# re-exported here so the logs section has one import surface.
from app.domain.admin.constants.admin import EmailLogStatus  # noqa: F401

# ─── Error codes (RM-ADMIN-LOG-NNN) ───────────────────────────────────────────

ERR_EMAIL_LOG_NOT_FOUND = "RM-ADMIN-LOG-001"
ERR_EMAIL_NOT_RETRIABLE = "RM-ADMIN-LOG-002"
ERR_EMAIL_RETRY_FAILED = "RM-ADMIN-LOG-003"

# ─── Default list ordering (applied when the request omits ?order_by=) ─────────

DEFAULT_EMAIL_LOGS_ORDER: list[str] = ["-created_at"]


# ─── Email category (drives retry behaviour) ──────────────────────────────────
class EmailCategory(str, Enum):
    OTP = "OTP"  # one-time codes — NOT retriable (a new OTP must be requested)
    BOOKING_CONFIRMATION = "BOOKING_CONFIRMATION"  # ticket email — re-dispatchable
    OTHER = "OTHER"


# ─── Template key (friendly identifier shown in the panel + template filter) ──
# Distinct from `category` (which drives retry): this is the human-facing label.
class EmailTemplateKey(str, Enum):
    OTP_VERIFY = "otp_verify"
    BOOKING_CONFIRMED = "booking_confirmed"
    # Future emails will add: waitlist_update, payment_failed, chart_prepared,
    # refund_processed — logged automatically once those senders pass a template.


# ─── Linked entity (the "LINKED" column — what this email is about) ───────────
class LinkedEntityType(str, Enum):
    PNR = "PNR"  # booking — navigate via booking_id
    USER = "USER"  # account — navigate via user_id
    TXN = "TXN"  # payment/transaction (future, when payment emails land)


# Only these categories can be re-sent from the panel. OTP is excluded on
# purpose: replaying an old code is meaningless and insecure.
RETRIABLE_EMAIL_CATEGORIES: frozenset[str] = frozenset(
    {EmailCategory.BOOKING_CONFIRMATION.value}
)
