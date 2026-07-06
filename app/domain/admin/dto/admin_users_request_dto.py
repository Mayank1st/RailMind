from typing import Literal, Optional

from pydantic import Field

from app.domain.auth.constants.auth_user import UserRole
from app.schemas.base import BaseDTO


# -- AdminUpdateUserRequest --------------------------------------
class AdminUpdateUserRequestDTO(BaseDTO):
    role: Optional[UserRole] = None  # USER | AGENT (Support) | ADMIN (Super)
    is_active: Optional[bool] = None  # false = deactivate/suspend
    reason: Optional[str] = Field(default=None, max_length=500)


# -- AdminKycReviewRequest ---------------------------------------
class AdminKycReviewRequestDTO(BaseDTO):
    decision: Literal["APPROVE", "REJECT"]
    reason: Optional[str] = Field(default=None, max_length=500)
