import uuid
from datetime import date, datetime

from sqlalchemy import Date, DateTime, ForeignKey, Index, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import DB_SCHEMA, BaseModel
from app.utils.helpers import get_utc_timezone


class SearchEvents(BaseModel):
    __tablename__ = "search_events"

    user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey(f"{DB_SCHEMA}.users.id", ondelete="SET NULL"),
        nullable=True,
    )
    session_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    source_station_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey(f"{DB_SCHEMA}.stations.id", ondelete="CASCADE"),
        nullable=False,
    )
    destination_station_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey(f"{DB_SCHEMA}.stations.id", ondelete="CASCADE"),
        nullable=False,
    )
    journey_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    train_class: Mapped[str | None] = mapped_column(String(5), nullable=True)
    quota: Mapped[str | None] = mapped_column(String(5), nullable=True)
    searched_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=get_utc_timezone, nullable=False
    )

    __table_args__ = (
        # Primary read path: the trending job's "last N days" window scan.
        Index("ix_search_events_searched_at", "searched_at"),
        {"schema": DB_SCHEMA},
    )

    def __repr__(self) -> str:
        return (
            f"<SearchEvents {self.source_station_id}->{self.destination_station_id} "
            f"at={self.searched_at}>"
        )
