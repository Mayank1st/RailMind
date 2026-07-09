from datetime import datetime
from typing import Optional

from app.core.filters import BaseFilter
from app.db.models.ai_prediction_log import AiPredictionLogs
from app.domain.admin.constants.admin_prediction_logs import (
    DEFAULT_PREDICTION_LOGS_ORDER,
)


# -- AdminPredictionLogFilter ------------------------------------
class AdminPredictionLogFilterDTO(BaseFilter):
    order_by: Optional[list[str]] = DEFAULT_PREDICTION_LOGS_ORDER
    advisor: Optional[str] = None
    advisor__in: Optional[list[str]] = None
    outcome: Optional[str] = None  # pending | hit | miss
    subject_ref: Optional[str] = None
    created_at__gte: Optional[datetime] = None
    created_at__lte: Optional[datetime] = None

    class Constants(
        BaseFilter.Constants
    ):  # naming: ignore — fastapi-filter inner class
        model = AiPredictionLogs
        search_model_fields = ["input_summary", "predicted_label", "subject_ref"]
