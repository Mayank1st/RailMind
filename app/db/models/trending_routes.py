import uuid
from datetime import date
from decimal import Decimal

from sqlalchemy import (
    Date,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import DB_SCHEMA, BaseModel


class TrendingRoutes(BaseModel):
    """Weekly demand snapshot cards computed from search_histories by the
    Sunday-night celery beat job. Station/train fields are denormalized on
    purpose — cards must render even if the underlying rows change later."""

    __tablename__ = "trending_routes"

    week_start: Mapped[date] = mapped_column(Date, nullable=False)
    demand_level: Mapped[str] = mapped_column(String(10), nullable=False)
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
    source_station_code: Mapped[str] = mapped_column(String(10), nullable=False)
    source_station_name: Mapped[str] = mapped_column(String(100), nullable=False)
    destination_station_code: Mapped[str] = mapped_column(String(10), nullable=False)
    destination_station_name: Mapped[str] = mapped_column(String(100), nullable=False)
    train_number: Mapped[str | None] = mapped_column(String(6), nullable=True)
    train_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    avg_duration_minutes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    min_fare: Mapped[Decimal | None] = mapped_column(Numeric(10, 2), nullable=True)
    search_count: Mapped[int] = mapped_column(Integer, nullable=False)

    __table_args__ = (
        UniqueConstraint("week_start", "demand_level", name="uq_trending_week_level"),
        # Primary read path: all cards for the latest computed week.
        Index("ix_trending_routes_week_start", "week_start"),
        {"schema": DB_SCHEMA},
    )

    def __repr__(self) -> str:
        return (
            f"<TrendingRoutes week={self.week_start} {self.demand_level} "
            f"{self.source_station_code}->{self.destination_station_code}>"
        )
