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


class PopularDestinations(BaseModel):
    """Weekly "Where India's heading" cards — top destinations by distinct
    searchers in search_events, computed by the Sunday-night beat job alongside
    trending routes. Denormalized snapshot: cards must render even if the
    underlying stations/trains change later. tagline is LLM-generated
    (train-type fallback when the call fails); image_url is the weekly
    carousel image (Supabase public URL, nano-banana-2 generated)."""

    __tablename__ = "popular_destinations"

    week_start: Mapped[date] = mapped_column(Date, nullable=False)
    rank: Mapped[int] = mapped_column(Integer, nullable=False)
    destination_station_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey(f"{DB_SCHEMA}.stations.id", ondelete="CASCADE"),
        nullable=False,
    )
    destination_station_code: Mapped[str] = mapped_column(String(10), nullable=False)
    destination_station_name: Mapped[str] = mapped_column(String(100), nullable=False)
    origin_station_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey(f"{DB_SCHEMA}.stations.id", ondelete="CASCADE"),
        nullable=False,
    )
    origin_station_code: Mapped[str] = mapped_column(String(10), nullable=False)
    origin_station_name: Mapped[str] = mapped_column(String(100), nullable=False)
    trains_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    train_number: Mapped[str | None] = mapped_column(String(6), nullable=True)
    train_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    min_fare: Mapped[Decimal | None] = mapped_column(Numeric(10, 2), nullable=True)
    tagline: Mapped[str | None] = mapped_column(String(60), nullable=True)
    image_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    search_count: Mapped[int] = mapped_column(Integer, nullable=False)

    __table_args__ = (
        UniqueConstraint("week_start", "rank", name="uq_popular_dest_week_rank"),
        # Primary read path: all cards for the latest computed week.
        Index("ix_popular_destinations_week_start", "week_start"),
        {"schema": DB_SCHEMA},
    )

    def __repr__(self) -> str:
        return (
            f"<PopularDestinations week={self.week_start} #{self.rank} "
            f"{self.destination_station_code}>"
        )
