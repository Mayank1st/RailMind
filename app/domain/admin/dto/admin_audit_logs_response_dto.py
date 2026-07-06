from datetime import datetime
from typing import Any

from app.schemas.base import BaseDTO


# -- AdminAuditLog (one activity row) ----------------------------
class AdminAuditLogResponseDTO(BaseDTO):
    audit_log_id: str
    actor_user_id: str | None  # who did it (null for system/unknown)
    actor_username: str | None
    action: str  # e.g. USER_ROLE_CHANGED
    target_type: str  # USER | KYC | BOOKING | ...
    target_id: str | None  # what was acted on
    before: dict[str, Any] | None  # state snapshot before the change
    after: dict[str, Any] | None  # state snapshot after the change
    reason: str | None
    ip: str | None
    created_at: datetime  # when
