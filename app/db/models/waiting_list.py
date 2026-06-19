from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    SmallInteger,
    String,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import BaseModel, DB_SCHEMA

# ──────────────────────────────────────────────────────────────────────────────
#  WAITLIST ENTRIES
# ──────────────────────────────────────────────────────────────────────────────


class WaitlistEntries(BaseModel):
    __tablename__ = "waitlists"

    booking_id: Mapped[UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey(f"{DB_SCHEMA}.bookings.id", ondelete="CASCADE"),
        nullable=False,
        index=True,  # ✅ simple single-column index — inline
    )
    booking_passenger_id: Mapped[UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey(f"{DB_SCHEMA}.booking_passengers.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,  # ✅ simple unique — inline
    )
    seat_inventory_id: Mapped[UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey(f"{DB_SCHEMA}.seat_inventories.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,  # ✅ simple single-column index — inline
    )
    train_class: Mapped[str] = mapped_column(String(5), nullable=False)
    quota: Mapped[str] = mapped_column(String(5), nullable=False)
    wl_type: Mapped[str] = mapped_column(String(10), nullable=False)
    booking_position: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    current_position: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    source_station_id: Mapped[UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey(f"{DB_SCHEMA}.stations.id", ondelete="RESTRICT"),
        nullable=False,
    )
    destination_station_id: Mapped[UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey(f"{DB_SCHEMA}.stations.id", ondelete="RESTRICT"),
        nullable=False,
    )
    is_promoted: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    promoted_to: Mapped[str | None] = mapped_column(String(5), nullable=True)
    promoted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    is_auto_cancelled: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False
    )
    auto_cancelled_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # ── Relationships ─────────────────────────────────────────────────────────
    booking = relationship("Bookings")
    booking_passenger = relationship("BookingPassengers", uselist=False)
    seat_inventory = relationship("SeatInventories")
    source_station = relationship("Stations", foreign_keys=[source_station_id])
    destination_station = relationship(
        "Stations", foreign_keys=[destination_station_id]
    )

    __table_args__ = (
        # ↓ compound index — can't do inline
        Index("ix_waitlists_wl_type_position", "wl_type", "current_position"),
        # ↓ partial indexes — can't do inline
        Index(
            "ix_waitlists_promotable",
            "seat_inventory_id",
            "wl_type",
            "current_position",
            postgresql_where="is_promoted = false AND is_auto_cancelled = false",
        ),
        Index(
            "ix_waitlists_active_by_inventory",
            "seat_inventory_id",
            postgresql_where="is_promoted = false AND is_auto_cancelled = false",
        ),
        {"schema": DB_SCHEMA},
    )
