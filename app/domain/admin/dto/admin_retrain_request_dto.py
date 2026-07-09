from pydantic import Field

from app.core.advisor_flags import AdvisorKey
from app.domain.admin.constants.admin_retrain import RetrainAlgorithm, TrainingWindow
from app.schemas.base import BaseDTO


# -- TriggerRetrainRequest ("Trigger retrain" modal) -------------
class TriggerRetrainRequestDTO(BaseDTO):
    advisor_key: AdvisorKey
    algorithm: RetrainAlgorithm
    training_window: TrainingWindow
    validation_split: int = Field(ge=5, le=50)  # percent
    gate_min_precision: float = Field(ge=0.0, le=1.0)
    gate_min_recall: float = Field(ge=0.0, le=1.0)


# -- PromoteCandidateRequest ("Promote to active?" modal) --------
class PromoteCandidateRequestDTO(BaseDTO):
    reason: str = Field(min_length=3, max_length=500)  # required
