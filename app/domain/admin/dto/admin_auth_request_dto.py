from typing import Annotated

from pydantic import EmailStr, Field

from app.schemas.base import BaseDTO


# -- AdminLoginRequest ---------------------------------------
class AdminLoginRequestDTO(BaseDTO):
    email: EmailStr
    password: Annotated[str, Field(min_length=1, max_length=128)]
    trust_device: bool = False  # "Trust this device" → longer-lived session


# -- AdminMfaVerifyRequest -----------------------------------
class AdminMfaVerifyRequestDTO(BaseDTO):
    code: Annotated[str, Field(pattern=r"^\d{6}$", examples=["827456"])]  # 6-digit TOTP
