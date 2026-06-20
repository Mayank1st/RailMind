from __future__ import annotations

import enum
from typing import TYPE_CHECKING, Optional

from sqlalchemy import ForeignKey, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import BaseModel, DB_SCHEMA

if TYPE_CHECKING:
    from app.db.models.user import Users


class UserActionType(str, enum.Enum):
    TRAIN_SEARCH = "TRAIN_SEARCH"
    AUTOFILL_REQUESTED = "AUTOFILL_REQUESTED"
    CLASS_SELECTED = "CLASS_SELECTED"
    BERTH_SELECTED = "BERTH_SELECTED"
    PASSENGER_ADDED = "PASSENGER_ADDED"
    BOOKING_INITIATED = "BOOKING_INITIATED"
    BOOKING_COMPLETED = "BOOKING_COMPLETED"
    FORM_ABANDONED = "FORM_ABANDONED"


class UserBehaviorLogs(BaseModel):
    __tablename__ = "user_behavior_logs"
    __table_args__ = ({"schema": DB_SCHEMA},)

    # nullable — guest actions bhi log honge
    user_id: Mapped[Optional[str]] = mapped_column(
        ForeignKey(f"{DB_SCHEMA}.users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    action_type: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        index=True,
    )

    # Flexible JSONB payload — schema varies per action_type
    # e.g. TRAIN_SEARCH: {source, destination, journey_date, class_filter}
    #      CLASS_SELECTED: {train_class, source, destination}
    #      BERTH_SELECTED: {berth_type, train_class}
    #      BOOKING_COMPLETED: {booking_id, train_class, berth_type, quota}
    action_metadata: Mapped[Optional[dict]] = mapped_column(
        JSONB,
        nullable=True,
    )

    session_id: Mapped[Optional[str]] = mapped_column(
        String(128),
        nullable=True,
        index=True,
    )

    device_type: Mapped[Optional[str]] = mapped_column(
        String(20),
        nullable=True,
    )

    # Stored as SHA256 hash for privacy
    ip_address: Mapped[Optional[str]] = mapped_column(
        String(64),
        nullable=True,
    )

    # ── Relationships ──────────────────────────────────────────────────────────
    user: Mapped[Optional["Users"]] = relationship(  # noqa: F821
        "Users",
        back_populates="behavior_logs",
        lazy="noload",
    )

    def __repr__(self) -> str:
        return (
            f"<UserBehaviorLogs id={self.id} user_id={self.user_id} "
            f"action_type={self.action_type}>"
        )
