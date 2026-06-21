from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import BaseModel, DB_SCHEMA
from sqlalchemy.dialects.postgresql import UUID


class UserOAuthAccounts(BaseModel):
    __tablename__ = "user_oauth_accounts"
    __table_args__ = (
        UniqueConstraint(
            "provider",
            "provider_user_id",
            name="uq_user_oauth_accounts_provider_provider_user_id",
        ),
        UniqueConstraint(
            "user_id",
            "provider",
            name="uq_user_oauth_accounts_user_id_provider",
        ),
        {"schema": DB_SCHEMA},
    )

    user_id: Mapped[UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey(f"{DB_SCHEMA}.users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    provider: Mapped[str] = mapped_column(String(20), nullable=False)
    provider_user_id: Mapped[str] = mapped_column(String(255), nullable=False)
    provider_email: Mapped[str] = mapped_column(String(255), nullable=False)
    picture_url: Mapped[str | None] = mapped_column(String(512), nullable=True)
    linked_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    last_used_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    user = relationship("Users", back_populates="user_oauth_accounts")

    def __repr__(self) -> str:
        return (
            f"<UserOAuthAccounts id={self.id} user_id={self.user_id} "
            f"provider={self.provider}>"
        )
