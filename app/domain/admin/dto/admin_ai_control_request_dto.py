from app.core.advisor_flags import AdvisorState
from app.schemas.base import BaseDTO


# -- SetAdvisorStateRequest (the Off / Force rules / On toggle) ---
class SetAdvisorStateRequestDTO(BaseDTO):
    state: AdvisorState
