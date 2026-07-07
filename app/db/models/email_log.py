from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import BaseModel, DB_SCHEMA


class EmailLogs(BaseModel):
    """Lifecycle record for every email the system sends (QUEUED → SENT/FAILED).

    Written best-effort by app/integrations/email.py at the single SMTP choke
    point; read by the admin console (Tier-1 Ops). Deliberately stores metadata
    only — never the rendered body, which would leak OTP codes and bloat the
    table. `user_id` / `booking_id` are nullable FKs (SET NULL on delete) so a
    log survives the deletion of its subject.
    """

    __tablename__ = "email_logs"

    to_email: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    subject: Mapped[str] = mapped_column(String(500), nullable=False)
    template: Mapped[str | None] = mapped_column(String(100), nullable=True)
    category: Mapped[str] = mapped_column(String(30), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    provider: Mapped[str | None] = mapped_column(String(100), nullable=True)
    provider_message_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    attempt_count: Mapped[int] = mapped_column(Integer, default=1, nullable=False)

    # Sanitized payload for the detail drawer — NEVER contains the OTP code.
    context: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    # "LINKED" column: what this email is about (PNR / USER / TXN) + a display
    # label; navigate via booking_id / user_id below.
    linked_type: Mapped[str | None] = mapped_column(String(10), nullable=True)
    linked_label: Mapped[str | None] = mapped_column(String(100), nullable=True)

    user_id: Mapped[UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey(f"{DB_SCHEMA}.users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    booking_id: Mapped[UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey(f"{DB_SCHEMA}.bookings.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    queued_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    sent_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    failed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    def __repr__(self) -> str:
        return (
            f"<EmailLogs id={self.id} to={self.to_email} "
            f"status={self.status} category={self.category}>"
        )
