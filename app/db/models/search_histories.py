import uuid
from datetime import date, datetime

from sqlalchemy import Date, DateTime, ForeignKey, Index, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import DB_SCHEMA, BaseModel
from app.utils.helpers import get_utc_timezone


class SearchHistories(BaseModel):
    __tablename__ = "search_histories"

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey(f"{DB_SCHEMA}.users.id", ondelete="CASCADE"),
        nullable=False,
    )
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
        UniqueConstraint(
            "user_id",
            "source_station_id",
            "destination_station_id",
            name="uq_search_user_route",
        ),
        # Primary read path: latest N searches for a user.
        Index("ix_search_histories_user_searched", "user_id", "searched_at"),
        {"schema": DB_SCHEMA},
    )

    def __repr__(self) -> str:
        return f"<SearchHistory user={self.user_id} {self.source_station_id}->{self.destination_station_id}>"
