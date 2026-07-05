# ─── Pre-auth (MFA-pending) token + cookie ────────────────────────────────────
# After the password step, super-admins get this short-lived token instead of a
# session. It only unlocks the 2FA endpoints; it is NOT a valid access token.

ADMIN_MFA_PENDING_COOKIE_NAME = "admin_mfa_pending"
ADMIN_MFA_PENDING_COOKIE_PATH = "/api/v1/admin"
ADMIN_MFA_PENDING_TTL_SECONDS = 300  # 5 min — matches the login-screen countdown

# ─── TOTP (Google Authenticator) ──────────────────────────────────────────────

TOTP_ISSUER = "RailMind Admin"  # label shown in the authenticator app
TOTP_DIGITS = 6
TOTP_INTERVAL_SECONDS = 30
TOTP_VALID_WINDOW = 1  # accept the adjacent 30s step for clock drift

# ─── Brute-force guard on the 2FA step ────────────────────────────────────────

ADMIN_MFA_MAX_ATTEMPTS = 5
ADMIN_MFA_ATTEMPT_PREFIX = "admin_mfa_attempts:"

# ─── Error codes ──────────────────────────────────────────────────────────────

ERR_INVALID_CREDENTIALS = "RM-ADMIN-AUTH-001"  # unknown email or wrong password
ERR_NOT_ADMIN = "RM-ADMIN-AUTH-002"  # role below AGENT — no console access
ERR_ACCOUNT_DISABLED = "RM-ADMIN-AUTH-003"  # is_active is false
ERR_GOOGLE_ONLY_ACCOUNT = "RM-ADMIN-AUTH-004"  # no password (OAuth-only) account
ERR_MFA_PENDING_INVALID = "RM-ADMIN-AUTH-005"  # missing/expired pre-auth token
ERR_MFA_CODE_INVALID = "RM-ADMIN-AUTH-006"  # wrong 6-digit code
ERR_MFA_TOO_MANY_ATTEMPTS = "RM-ADMIN-AUTH-007"  # brute-force lock
ERR_MFA_NOT_SET_UP = "RM-ADMIN-AUTH-008"  # verify called before setup
ERR_MFA_ALREADY_ENABLED = "RM-ADMIN-AUTH-009"  # setup called after enrolment
