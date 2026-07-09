from datetime import date
from typing import Optional

from app.schemas.base import BaseDTO


# -- ModelAdvisorRow (one row of the Model Versions table) -------
class ModelAdvisorRowDTO(BaseDTO):
    advisor_key: str  # ADVISOR
    name: str  # "Waitlist Predictor"
    active_version: str  # ACTIVE VERSION — what's actually serving now
    key_metric: str  # KEY METRIC line
    serving_status: str  # live | fallback | off (STATUS badge)


# -- ModelVersionItem (one version-history card) -----------------
class ModelVersionItemDTO(BaseDTO):
    version_label: str  # "waitlist-predictor-v1"
    kind: str  # ml | fallback
    metrics_summary: str  # "Precision 0.95 · Recall 0.94" | "Rule-based fallback"
    trained_at: Optional[date]  # None for the fallback
    status: str  # active | previous | archived | fallback
    in_use: bool  # is THIS version actually serving right now
    artifact_available: bool  # ML artifact present on disk (activatable)


# -- ModelVersionHistory (the Manage drawer) ---------------------
class ModelVersionHistoryDTO(BaseDTO):
    advisor_key: str
    name: str
    currently_serving: str  # version_label being served now
    versions: list[ModelVersionItemDTO]
