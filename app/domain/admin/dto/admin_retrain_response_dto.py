from datetime import datetime
from typing import Optional

from app.schemas.base import BaseDTO


# -- RetrainCandidateItem (one row of the Retrain table) ---------
class RetrainCandidateItemDTO(BaseDTO):
    candidate_id: str
    candidate_label: str  # CANDIDATE "wl-xgb-rc-1"
    advisor_key: str
    advisor_name: str  # ADVISOR "Waitlist Predictor"
    precision: Optional[float]  # PRECISION (None until trained)
    recall: Optional[float]  # RECALL
    gate_passed: Optional[bool]
    gate_status: str  # passed | failed | pending (GATE badge)
    status: str  # QUEUED | RUNNING | TRAINED | PROMOTED | REJECTED | FAILED
    trained_at: Optional[datetime]  # TRAINED
    can_promote: bool  # trained + gate passed + not already promoted


# -- RetrainReport (the "View report" drawer) --------------------
class RetrainReportDTO(BaseDTO):
    candidate_id: str
    candidate_label: str
    advisor_key: str
    advisor_name: str
    status: str
    gate_status: str
    gate_passed: Optional[bool]

    algorithm: str
    training_window: str  # human label
    validation_split: int

    precision: Optional[float]
    recall: Optional[float]
    gate_min_precision: float
    gate_min_recall: float
    precision_vs_baseline: Optional[float]  # +0.02
    recall_vs_baseline: Optional[float]

    confusion: Optional[dict]  # {tp, fp, fn, tn}
    feature_importance: Optional[list]  # [{feature, importance}]
    rows_trained: Optional[int]
    duration_seconds: Optional[int]
    trained_at: Optional[datetime]
    error: Optional[str]

    promoted_at: Optional[datetime]
    promote_reason: Optional[str]
    can_promote: bool
