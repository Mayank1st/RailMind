from datetime import date, datetime

from sqlalchemy import Boolean, Date, DateTime, Enum as SAEnum, ForeignKey, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.constants.auth_user import Gender, KycStatus, MaritalStatus, UserRole
from app.db.base import BaseModel, DB_SCHEMA


class Users(BaseModel):
    __tablename__ = "users"

    username: Mapped[str] = mapped_column(
        String(30), unique=True, nullable=False, index=True
    )
    email: Mapped[str] = mapped_column(
        String(255), unique=True, nullable=False, index=True
    )
    password: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[str] = mapped_column(
        String(20),
        default=UserRole.USER,
        nullable=False,
        index=True,
    )
    is_email_verified: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False
    )
    is_mobile_verified: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False
    )
    preferred_language: Mapped[str] = mapped_column(
        String(30), default="English", nullable=False
    )
    security_question: Mapped[str] = mapped_column(String(255), nullable=False)
    security_answer_hash: Mapped[str] = mapped_column(String(255), nullable=False)

    user_profile = relationship(
        "UserProfiles",
        back_populates="user",
        uselist=False,
        cascade="all, delete-orphan",
    )
    user_contact = relationship(
        "UserContacts",
        back_populates="user",
        uselist=False,
        cascade="all, delete-orphan",
    )
    user_kyc = relationship(
        "UserKYC",
        back_populates="user",
        uselist=False,
        cascade="all, delete-orphan",
    )

    passengers = relationship(
        "Passengers",
        back_populates="user",
        cascade="all, delete-orphan",
    )


class UserProfiles(BaseModel):
    __tablename__ = "user_profiles"

    user_id: Mapped[UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey(f"{DB_SCHEMA}.users.id", ondelete="CASCADE"),
        unique=True,
        nullable=False,
    )
    first_name: Mapped[str] = mapped_column(String(50), nullable=False)
    last_name: Mapped[str] = mapped_column(String(50), nullable=False)
    gender: Mapped[Gender] = mapped_column(
        SAEnum(Gender, name="gender_enum"), nullable=False
    )
    date_of_birth: Mapped[date | None] = mapped_column(Date)
    marital_status: Mapped[MaritalStatus] = mapped_column(
        SAEnum(MaritalStatus, name="marital_status_enum"), nullable=False
    )
    nationality: Mapped[str | None] = mapped_column(String(50))
    occupation_type: Mapped[str | None] = mapped_column(String(50))
    occupation: Mapped[str | None] = mapped_column(String(100))

    user = relationship("Users", back_populates="user_profile")


class UserContacts(BaseModel):
    __tablename__ = "user_contacts"

    user_id: Mapped[UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey(f"{DB_SCHEMA}.users.id", ondelete="CASCADE"),
        unique=True,
        nullable=False,
    )
    mobile_number: Mapped[str] = mapped_column(String(15), nullable=False)
    address_line1: Mapped[str | None] = mapped_column(String(100))
    street: Mapped[str | None] = mapped_column(String(100))
    state: Mapped[str | None] = mapped_column(String(50))
    pin_code: Mapped[str | None] = mapped_column(String(10))
    country: Mapped[str | None] = mapped_column(String(50))
    landline_number: Mapped[str | None] = mapped_column(String(15))

    user = relationship("Users", back_populates="user_contact")


class UserKYC(BaseModel):
    __tablename__ = "user_kyc"

    user_id: Mapped[UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey(f"{DB_SCHEMA}.users.id", ondelete="CASCADE"),
        unique=True,
        nullable=False,
    )
    # Store HMAC-SHA256 hex (64 chars) for deduplication; not plaintext Aadhaar/PAN.
    aadhaar_number: Mapped[str | None] = mapped_column(String(64))
    pan_number: Mapped[str | None] = mapped_column(String(64))
    kyc_status: Mapped[KycStatus] = mapped_column(
        SAEnum(KycStatus, name="kyc_status_enum"), default=KycStatus.PENDING
    )
    verified_at: Mapped[datetime | None] = mapped_column(DateTime)

    user = relationship("Users", back_populates="user_kyc")
