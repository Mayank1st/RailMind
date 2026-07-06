import uuid
from datetime import datetime
from typing import Optional

from app.core.filters import BaseFilter
from app.db.models.admin_audit_log import AdminAuditLogs
from app.domain.admin.constants.admin_audit import DEFAULT_AUDIT_LOGS_ORDER


# -- AdminAuditLogFilter -----------------------------------------
class AdminAuditLogFilterDTO(BaseFilter):
    order_by: Optional[list[str]] = DEFAULT_AUDIT_LOGS_ORDER
    action: Optional[str] = None
    action__in: Optional[list[str]] = None
    target_type: Optional[str] = None
    target_id: Optional[str] = None
    actor_user_id: Optional[uuid.UUID] = None
    actor_username: Optional[str] = None
    actor_username__ilike: Optional[str] = None
    created_at__gte: Optional[datetime] = None
    created_at__lte: Optional[datetime] = None

    class Constants(
        BaseFilter.Constants
    ):  # naming: ignore — fastapi-filter inner class
        model = AdminAuditLogs
        search_model_fields = ["actor_username", "action", "target_id"]
