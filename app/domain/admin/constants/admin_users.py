# Admin Users — Entities → Users subsection (search, roles, KYC queue).
#
# Read-only over existing Users / UserProfiles / UserContacts / UserKYC / Bookings.
# Actions (role assign, deactivate, KYC approve/reject) are super-admin-only and
# every one is audit-logged (see admin_audit_service). Role display labels map to
# the existing UserRole enum: USER→USER, Support→AGENT, Super→ADMIN.

from app.domain.auth.constants.auth_user import UserRole

# ─── Error codes (RM-ADMIN-USR-NNN) ───────────────────────────────────────────

ERR_USER_NOT_FOUND = "RM-ADMIN-USR-001"
ERR_USER_NO_CHANGES = "RM-ADMIN-USR-002"
ERR_USER_SELF_MODIFY = "RM-ADMIN-USR-003"  # can't change your own role / disable self
ERR_KYC_NOT_FOUND = "RM-ADMIN-USR-004"

# ─── Roles assignable from the panel (GUEST is never assignable) ──────────────

ASSIGNABLE_ROLES = (UserRole.USER.value, UserRole.AGENT.value, UserRole.ADMIN.value)

# UI label ↔ backend role value (FE may send either; backend normalizes).
ROLE_LABELS = {
    UserRole.USER.value: "USER",
    UserRole.AGENT.value: "Support",
    UserRole.ADMIN.value: "Super",
}

# ─── Status labels (Users.is_active → UI) ─────────────────────────────────────

STATUS_ACTIVE = "active"
STATUS_SUSPENDED = "suspended"

# ─── Default list ordering ────────────────────────────────────────────────────

DEFAULT_USERS_ORDER = "-created_at"
