from app.db.base import BaseModel, DB_SCHEMA
from sqlalchemy.orm import Mapped, mapped_column, relationship
from typing import Optional
from datetime import datetime
from sqlalchemy import (
    String,
    JSON,
    DateTime,
    ForeignKey,
    String,
    SmallInteger,
    DateTime,
    Enum as SAEnum,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from app.domain.booking.constants.booking_retry_request import (
    BookingRetryRequestStatus,
    RetryFailureReason,
)
from app.db.models.booking import Bookings
from app.db.models.user import Users


class BookingRetryRequest(BaseModel):
    __tablename__ = "booking_retry_request"
    __table_args__ = ({"schema": DB_SCHEMA},)

    booking_id: Mapped[UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey(f"{DB_SCHEMA}.bookings.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    user_id: Mapped[UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey(f"{DB_SCHEMA}.users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    failure_reason: Mapped[str] = mapped_column(
        SAEnum(
            RetryFailureReason,
            name="retry_failure_reason",
            schema=DB_SCHEMA,
        ),
        nullable=False,
    )
    original_payload: Mapped[dict] = mapped_column(JSON, nullable=False)
    status: Mapped[str] = mapped_column(
        SAEnum(
            BookingRetryRequestStatus,
            name="booking_retry_status",
            schema=DB_SCHEMA,
        ),
        nullable=False,
        default=BookingRetryRequestStatus.PENDING,
        index=True,
    )
    attempt_count: Mapped[int] = mapped_column(SmallInteger, nullable=False, default=0)
    max_attempts: Mapped[int] = mapped_column(SmallInteger, nullable=False, default=6)
    last_attempted_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    next_retry_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        index=True,
    )
    success_booking_id: Mapped[Optional[UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey(f"{DB_SCHEMA}.bookings.id", ondelete="SET NULL"),
        nullable=True,
    )

    # ── Relationships ─────────────────────────────────────────────────────────
    user: Mapped["Users"] = relationship(
        "Users",
        foreign_keys=[user_id],
        lazy="noload",
    )
    booking: Mapped["Bookings"] = relationship(
        "Bookings",
        foreign_keys=[booking_id],
        lazy="noload",
    )
    success_booking: Mapped[Optional["Bookings"]] = relationship(
        "Bookings",
        foreign_keys=[success_booking_id],
        lazy="noload",
    )

    def __repr__(self) -> str:
        return (
            f"<BookingRetryRequest id={self.id} booking_id={self.booking_id} "
            f"status={self.status}>"
        )
