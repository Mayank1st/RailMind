import uuid
from datetime import datetime
from typing import Optional

from app.core.filters import BaseFilter
from app.db.models.error_log import ErrorLogs
from app.domain.admin.constants.admin_errors import DEFAULT_ERROR_LOGS_ORDER


# -- AdminErrorLogFilter -----------------------------------------
class AdminErrorLogFilterDTO(BaseFilter):
    order_by: Optional[list[str]] = DEFAULT_ERROR_LOGS_ORDER
    code: Optional[str] = None
    code__in: Optional[list[str]] = None
    domain: Optional[str] = None
    severity: Optional[str] = None  # ERROR | WARNING
    status_code: Optional[int] = None
    method: Optional[str] = None
    path: Optional[str] = None
    path__ilike: Optional[str] = None
    user_id: Optional[uuid.UUID] = None
    created_at__gte: Optional[datetime] = None
    created_at__lte: Optional[datetime] = None

    class Constants(
        BaseFilter.Constants
    ):  # naming: ignore — fastapi-filter inner class
        model = ErrorLogs
        search_model_fields = ["code", "message", "path"]
