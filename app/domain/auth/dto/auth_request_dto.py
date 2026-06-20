import re
from datetime import date
from typing import Annotated, Optional

from pydantic import EmailStr, Field, field_validator, model_validator
from app.domain.auth.constants.auth_user import UserRole

from app.domain.auth.constants.auth_user import (
    AllOccupations,
    Gender,
    MaritalStatus,
    OccupationType,
)
from app.schemas.base import BaseDTO


# -- CreateAccount -------------------------------------------
class CreateAccountDTO(BaseDTO):
    pass


# -- BasicAccountDetails -------------------------------------
class BasicAccountDetailsDTO(CreateAccountDTO):

    username: Annotated[
        str,
        Field(
            min_length=3,
            max_length=30,
            examples=["mayank1st"],
            description="Unique username (3-30 characters)",
        ),
    ]

    password: Annotated[
        str,
        Field(
            min_length=8,
            max_length=50,
            examples=["Test@1234"],
            description=(
                "Strong password.\n\n"
                "Requirements:\n"
                "- Minimum 8 characters\n"
                "- At least 1 uppercase letter (A-Z)\n"
                "- At least 1 number (0-9)\n"
                "- At least 1 special character from: @ $ ! % * ? &"
            ),
        ),
    ]

    @field_validator("password")
    @classmethod
    def password_strength(cls, v: str) -> str:
        if not re.search(r"[A-Z]", v):
            raise ValueError("Password must contain at least one uppercase letter")
        if not re.search(r"\d", v):
            raise ValueError("Password must contain at least one digit")
        if not re.search(r"[@$!%*?&]", v):
            raise ValueError(
                "Password must contain at least one special character from @$!%*?&"
            )
        return v

    confirm_password: Annotated[
        str,
        Field(
            min_length=8,
            max_length=50,
            examples=["Test@1234"],
            description="Must match the password field",
        ),
    ]

    preferred_language: Annotated[
        str,
        Field(
            default="English",
            min_length=2,
            max_length=30,
            examples=["English"],
            description="User's preferred language",
        ),
    ]

    security_question: Annotated[
        str,
        Field(
            min_length=5,
            max_length=200,
            examples=["What was the name of your first school?"],
        ),
    ]

    security_answer: Annotated[
        str,
        Field(
            min_length=2,
            max_length=100,
            examples=["Test School"],
            description="Answer will be stored in hashed format",
        ),
    ]

    @model_validator(mode="after")
    def validate_passwords_match(self):
        if self.password != self.confirm_password:
            raise ValueError("Password and Confirm Password do not match")
        return self


# -- PersonalDetails -----------------------------------------
class PersonalDetailsDTO(BasicAccountDetailsDTO):

    first_name: Annotated[
        str,
        Field(min_length=2, max_length=50, examples=["Mayank"]),
    ]

    last_name: Annotated[
        str,
        Field(min_length=2, max_length=50, examples=["Kumar"]),
    ]

    gender: Annotated[
        Gender,
        Field(min_length=1, max_length=20, examples=["Male"]),
    ]

    date_of_birth: Annotated[
        date,
        Field(
            examples=["1998-09-24"],
            description="Date format: YYYY-MM-DD",
        ),
    ]

    occupation_type: OccupationType = Field(default=OccupationType.CORPORATE_OR_PRIVATE)

    occupation: AllOccupations = Field(
        description="Occupation based on selected occupation type"
    )

    marital_status: MaritalStatus = Field(default=MaritalStatus.UNMARRIED)

    nationality: Annotated[
        str,
        Field(default="INDIA", min_length=2, max_length=50),
    ]

    aadhaar_number: Optional[
        Annotated[
            str,
            Field(
                pattern=r"^\d{12}$",
                description="12-digit Aadhaar number",
                examples=["123412341234"],
            ),
        ]
    ] = None

    pan_number: Optional[
        Annotated[
            str,
            Field(
                pattern=r"^[A-Z]{5}[0-9]{4}[A-Z]{1}$",
                description="PAN format: ABCDE1234F",
                examples=["ABCDE1234F"],
            ),
        ]
    ] = None


# -- ContactDetails ------------------------------------------
class ContactDetailsDTO(PersonalDetailsDTO):

    email: EmailStr = Field(
        examples=["mayank@email.com"],
        description="User email (OTP verified)",
    )

    mobile_number: Annotated[
        str,
        Field(
            pattern=r"^[6-9]\d{9}$",
            examples=["9876543210"],
            description="Valid 10-digit Indian mobile number",
        ),
    ]

    address_line1: Annotated[
        str,
        Field(min_length=3, max_length=100),
    ]

    street: Annotated[
        str,
        Field(min_length=3, max_length=100),
    ]

    state: Annotated[
        str,
        Field(min_length=2, max_length=50),
    ]

    pin_code: Annotated[
        str,
        Field(
            pattern=r"^\d{6}$",
            description="6-digit Indian PIN code",
            examples=["826001"],
        ),
    ]

    country: Annotated[
        str,
        Field(default="INDIA", min_length=2, max_length=50),
    ]

    landline_number: Optional[
        Annotated[
            str,
            Field(
                pattern=r"^\d{6,10}$",
                description="Optional landline number",
            ),
        ]
    ] = None


# -- LoginRequest --------------------------------------------
class LoginRequestDTO(BaseDTO):
    email: Optional[str] = None
    username: Optional[str] = None
    password: str


# -- SendOtp -------------------------------------------------
class SendOtpDTO(BaseDTO):
    email: str


# -- VerifyOtp -----------------------------------------------
class VerifyOtpDTO(BaseDTO):
    email: str
    otp: str


# -- UserProfile ---------------------------------------------
class UserProfileDTO(BaseDTO):
    id: str
    username: str
    email: str
    role: UserRole
    is_email_verified: bool
    is_mobile_verified: bool
    preferred_language: str
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    gender: Optional[Gender] = None
    date_of_birth: Optional[date] = None
    marital_status: Optional[MaritalStatus] = None
    nationality: Optional[str] = None
    occupation: Optional[str] = None
    mobile_number: Optional[str] = None
    address_line1: Optional[str] = None
    street: Optional[str] = None
    state: Optional[str] = None
    pin_code: Optional[str] = None
    country: Optional[str] = None
    kyc_status: Optional[str] = None


# -- UpdateUserProfile ---------------------------------------
class UpdateUserProfileDTO(BaseDTO):
    """
    Partial user profile update schema.
    All fields are optional — user can update one or more fields at once.
    """

    preferred_language: Optional[str] = Field(None, min_length=2, max_length=30)
    first_name: Optional[str] = Field(None, min_length=2, max_length=50)
    last_name: Optional[str] = Field(None, min_length=2, max_length=50)
    gender: Optional[Gender] = None
    date_of_birth: Optional[date] = None
    marital_status: Optional[MaritalStatus] = None
    nationality: Optional[str] = Field(None, min_length=2, max_length=50)
    occupation_type: Optional[OccupationType] = None
    occupation: Optional[str] = Field(None, max_length=100)
    address_line1: Optional[str] = Field(None, min_length=3, max_length=100)
    street: Optional[str] = Field(None, min_length=3, max_length=100)
    state: Optional[str] = Field(None, min_length=2, max_length=50)
    pin_code: Optional[str] = Field(None, pattern=r"^\d{6}$")
    country: Optional[str] = Field(None, min_length=2, max_length=50)
    landline_number: Optional[str] = Field(None, pattern=r"^\d{6,10}$")
    aadhaar_number: Optional[str] = Field(None, pattern=r"^\d{12}$")
    pan_number: Optional[str] = Field(None, pattern=r"^[A-Z]{5}[0-9]{4}[A-Z]{1}$")
    mobile_number: Optional[str] = None
