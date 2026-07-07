# Admin Ops — Bookings/PNR + Payments/Refunds oversight (read-only surface).
#
# Support/agent-facing observability over existing business tables. No new
# tables are introduced here: every endpoint reads Bookings / Payments / Refunds
# that already exist. Action endpoints (cancel/refund) are intentionally NOT here
# — they require the admin_audit_logs table (plan §4.3) and a refund service that
# does not exist yet, so they ship in a later phase.

# ─── Error codes (RM-ADMIN-OPS-NNN) ───────────────────────────────────────────

ERR_BOOKING_NOT_FOUND = "RM-ADMIN-OPS-001"

# ─── Default list ordering (applied when the request omits ?order_by=) ─────────
# Support needs the most recent activity first, so every list defaults to newest.

DEFAULT_BOOKINGS_ORDER: list[str] = ["-booked_at"]
DEFAULT_PAYMENTS_ORDER: list[str] = ["-initiated_at"]
DEFAULT_REFUNDS_ORDER: list[str] = ["-initiated_at"]
