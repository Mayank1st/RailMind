from datetime import datetime
from typing import Optional

from app.schemas.base import BaseDTO


# -- PredictionLogItem (one row of the Prediction Logs table) ----
class PredictionLogItemDTO(BaseDTO):
    prediction_log_id: str
    created_at: datetime  # TIME
    advisor: str  # ADVISOR
    input_summary: str  # INPUT
    predicted_label: str  # PREDICTED
    predicted_confidence: Optional[float]
    actual_label: Optional[str]  # ACTUAL (null while pending)
    outcome: str  # MATCH: pending | hit | miss
    subject_ref: Optional[str]
