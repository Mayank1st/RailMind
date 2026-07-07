# Admin email-logs list filter.
#
# Built on `fastapi-filter` (see app/core/filters.py). Query params auto-map to
# WHERE clauses via operator suffixes (__ilike / __in / __gte / __lte). Defaults
# to newest-first so support sees the most recent sends.

import uuid
from datetime import datetime
from typing import Optional

from app.core.filters import BaseFilter
from app.db.models.email_log import EmailLogs
from app.domain.admin.constants.admin_logs import DEFAULT_EMAIL_LOGS_ORDER


# -- AdminEmailLogFilter -----------------------------------------
class AdminEmailLogFilterDTO(BaseFilter):
    order_by: Optional[list[str]] = DEFAULT_EMAIL_LOGS_ORDER
    status: Optional[str] = None
    status__in: Optional[list[str]] = None
    category: Optional[str] = None
    template: Optional[str] = None
    to_email: Optional[str] = None
    to_email__ilike: Optional[str] = None
    user_id: Optional[uuid.UUID] = None
    booking_id: Optional[uuid.UUID] = None
    created_at__gte: Optional[datetime] = None
    created_at__lte: Optional[datetime] = None

    class Constants(
        BaseFilter.Constants
    ):  # naming: ignore — fastapi-filter inner class
        model = EmailLogs
        search_model_fields = ["to_email", "subject"]
