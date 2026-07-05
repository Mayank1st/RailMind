from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import BaseModel, DB_SCHEMA


class AdminMfaSecrets(BaseModel):
    """TOTP (Google Authenticator) secret for an admin-console user.

    One row per admin user. The secret is stored Fernet-encrypted (never in
    plaintext); `is_enabled` flips true only after the user confirms the first
    6-digit code during setup. Kept in its own table so the sensitive secret
    stays out of the frequently-loaded `users` row.
    """

    __tablename__ = "admin_mfa_secrets"

    user_id: Mapped[UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey(f"{DB_SCHEMA}.users.id", ondelete="CASCADE"),
        unique=True,
        nullable=False,
    )
    secret_encrypted: Mapped[str] = mapped_column(Text, nullable=False)
    is_enabled: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    confirmed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    last_used_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    def __repr__(self) -> str:
        return (
            f"<AdminMfaSecrets id={self.id} user_id={self.user_id} "
            f"enabled={self.is_enabled}>"
        )
