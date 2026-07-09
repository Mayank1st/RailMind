from enum import Enum

# ─── Error codes (RM-ADMIN-RTR-NNN) ───────────────────────────────────────────

ERR_RETRAIN_NOT_FOUND = "RM-ADMIN-RTR-001"
ERR_RETRAIN_GATE_NOT_PASSED = "RM-ADMIN-RTR-002"  # can't promote a failed candidate
ERR_RETRAIN_NOT_TRAINED = "RM-ADMIN-RTR-003"  # can't promote before results are in
ERR_RETRAIN_ALREADY_PROMOTED = "RM-ADMIN-RTR-004"
ERR_RETRAIN_ADVISOR_NOT_FOUND = "RM-ADMIN-RTR-005"


# ─── Lifecycle status ─────────────────────────────────────────────────────────
class RetrainStatus(str, Enum):
    QUEUED = "QUEUED"  # requested; awaiting the training runner
    RUNNING = "RUNNING"  # runner picked it up
    TRAINED = "TRAINED"  # result registered; reviewable
    PROMOTED = "PROMOTED"  # promoted to active
    REJECTED = "REJECTED"  # reviewed and discarded
    FAILED = "FAILED"  # training errored


# ─── Trigger options ──────────────────────────────────────────────────────────
class RetrainAlgorithm(str, Enum):
    XGBOOST = "XGBoost"
    LIGHTGBM = "LightGBM"
    NEURAL_NET = "NeuralNet"


class TrainingWindow(str, Enum):
    LAST_3_MONTHS = "LAST_3_MONTHS"
    LAST_6_MONTHS = "LAST_6_MONTHS"
    LAST_12_MONTHS = "LAST_12_MONTHS"
    ALL_TIME = "ALL_TIME"


TRAINING_WINDOW_LABELS = {
    TrainingWindow.LAST_3_MONTHS.value: "Last 3 months",
    TrainingWindow.LAST_6_MONTHS.value: "Last 6 months",
    TrainingWindow.LAST_12_MONTHS.value: "Last 12 months",
    TrainingWindow.ALL_TIME.value: "All time",
}

# ─── Gate ─────────────────────────────────────────────────────────────────────

DEFAULT_GATE_MIN_PRECISION = 0.90
DEFAULT_GATE_MIN_RECALL = 0.88

GATE_STATUS_PASSED = "passed"
GATE_STATUS_FAILED = "failed"
GATE_STATUS_PENDING = "pending"

# ─── Candidate label generation ("wl-xgb-rc-1") ───────────────────────────────

CANDIDATE_FAMILY = {"waitlist": "wl", "fare": "fare", "autofill": "af"}
ALGO_ABBR = {
    RetrainAlgorithm.XGBOOST.value: "xgb",
    RetrainAlgorithm.LIGHTGBM.value: "lgbm",
    RetrainAlgorithm.NEURAL_NET.value: "nn",
}
