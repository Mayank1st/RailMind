from datetime import date

from sqlalchemy import BigInteger, Date, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import BaseModel, DB_SCHEMA


class DailySeatOccupancies(BaseModel):
    """Precomputed daily seat-occupancy rollup — one row per journey_date,
    aggregating the multi-million-row `seat_inventories` table so the admin
    Overview endpoint reads a handful of days instead of seq-scanning the whole
    table. Refreshed off the request path by a celery-beat task; a few minutes
    of staleness is fine for a dashboard.
    """

    __tablename__ = "daily_seat_occupancies"

    journey_date: Mapped[date] = mapped_column(Date, nullable=False)
    total_confirmed_seats: Mapped[int] = mapped_column(
        BigInteger, nullable=False, default=0
    )
    booked_confirmed_seats: Mapped[int] = mapped_column(
        BigInteger, nullable=False, default=0
    )

    __table_args__ = (
        UniqueConstraint("journey_date", name="uq_daily_seat_occupancies_journey_date"),
        {"schema": DB_SCHEMA},
    )

    def __repr__(self) -> str:
        return (
            f"<DailySeatOccupancies date={self.journey_date} "
            f"booked={self.booked_confirmed_seats}/{self.total_confirmed_seats}>"
        )
