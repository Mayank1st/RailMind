# ─── Error codes (RM-ADMIN-ERR-NNN) ───────────────────────────────────────────

ERR_ERROR_LOG_NOT_FOUND = "RM-ADMIN-ERR-001"

# ─── Read-side defaults ───────────────────────────────────────────────────────

DEFAULT_ERROR_LOGS_ORDER: list[str] = ["-created_at"]
TOP_ERROR_CODES_LIMIT = 10  # "top offending codes" in the summary
