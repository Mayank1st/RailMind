from datetime import date, datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    Date,
    Float,
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
#  BOOKINGS
# ──────────────────────────────────────────────────────────────────────────────


class Bookings(BaseModel):
    __tablename__ = "bookings"

    user_id: Mapped[UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey(f"{DB_SCHEMA}.users.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    train_id: Mapped[UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey(f"{DB_SCHEMA}.trains.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    pnr_number: Mapped[str] = mapped_column(String(10), nullable=False, unique=True)
    booking_status: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    journey_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    source_station_id: Mapped[UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey(f"{DB_SCHEMA}.stations.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    destination_station_id: Mapped[UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey(f"{DB_SCHEMA}.stations.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    train_class: Mapped[str] = mapped_column(String(5), nullable=False)
    quota: Mapped[str] = mapped_column(String(5), nullable=False)
    total_fare: Mapped[float] = mapped_column(Float, nullable=False)
    booked_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    # ── Relationships ──────────────────────────────────────────────────────
    user = relationship("Users", back_populates="bookings", lazy="noload")
    train = relationship("Trains", lazy="noload")
    source_station = relationship(
        "Stations", foreign_keys=[source_station_id], lazy="noload"
    )
    destination_station = relationship(
        "Stations", foreign_keys=[destination_station_id], lazy="noload"
    )

    booking_passengers = relationship(
        "BookingPassengers",
        back_populates="booking",
        cascade="all, delete-orphan",
    )

    waitlist_entries = relationship(
        "WaitlistEntries",
        back_populates="booking",
        cascade="all, delete-orphan",
        lazy="noload",
    )

    payments = relationship(
        "Payments",
        back_populates="booking",
        cascade="all, delete-orphan",
        lazy="noload",
    )

    refunds = relationship(
        "Refunds",
        back_populates="booking",
        cascade="all, delete-orphan",
        lazy="noload",
    )

    __table_args__ = (
        Index("ix_bookings_user_status", "user_id", "booking_status"),
        {"schema": DB_SCHEMA},
    )

    def __repr__(self) -> str:
        return f"<Bookings PNR={self.pnr_number} status={self.booking_status}>"


# ──────────────────────────────────────────────────────────────────────────────
#  BOOKING PASSENGERS
# ──────────────────────────────────────────────────────────────────────────────


class BookingPassengers(BaseModel):

    __tablename__ = "booking_passengers"

    booking_id: Mapped[UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey(f"{DB_SCHEMA}.bookings.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    # NULL for WL/RAC passengers until seat is physically assigned
    seat_id: Mapped[UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey(f"{DB_SCHEMA}.seats.id", ondelete="SET NULL"),
        nullable=True,
    )
    # Denormalised for fast promotion-engine queries — avoids joining through bookings
    seat_inventory_id: Mapped[UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey(f"{DB_SCHEMA}.seat_inventories.id", ondelete="RESTRICT"),
        nullable=False,
    )
    passenger_id: Mapped[UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey(f"{DB_SCHEMA}.passengers.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    # BerthPreference enum: "LB", "MB", "UB", "SL", "SU", "NP"
    berth_preference: Mapped[str] = mapped_column(
        String(5), nullable=False, default="NP"
    )
    # Actual berth assigned (e.g. "LB", "UB"). NULL until assigned at chart time.
    allotted_berth: Mapped[str | None] = mapped_column(String(5), nullable=True)
    # PassengerStatus enum: "CNF" / "RAC" / "WL" / "CAN"
    passenger_status: Mapped[str] = mapped_column(String(5), nullable=False, index=True)
    fare: Mapped[float] = mapped_column(Float, nullable=False)

    booking = relationship("Bookings", back_populates="booking_passengers")
    passenger = relationship("Passengers")
    seat = relationship("Seats")
    seat_inventory = relationship("SeatInventories")
    # A WL passenger has one WaitlistEntries row; CNF/RAC passengers have none
    waitlist_entry = relationship(
        "WaitlistEntries",
        back_populates="booking_passenger",
        uselist=False,
    )
    # An RAC passenger occupies one slot on a RACSlots row
    rac_slot_as_passenger_1 = relationship(
        "RACSlots",
        foreign_keys="RACSlots.passenger_1_booking_passenger_id",
        back_populates="passenger_1",
        uselist=False,
    )
    rac_slot_as_passenger_2 = relationship(
        "RACSlots",
        foreign_keys="RACSlots.passenger_2_booking_passenger_id",
        back_populates="passenger_2",
        uselist=False,
    )

    __table_args__ = (
        # compound index — can't do inline
        Index("ix_bkng_passengers_inv_status", "seat_inventory_id", "passenger_status"),
        {"schema": DB_SCHEMA},
    )

    def __repr__(self) -> str:
        return (
            f"<BookingPassengers passenger={self.passenger_id} "
            f"status={self.passenger_status} booking={self.booking_id}>"
        )


# ──────────────────────────────────────────────────────────────────────────────
#  RAC SLOTS
# ──────────────────────────────────────────────────────────────────────────────


class RACSlots(BaseModel):
    """
    One physical RAC side-lower berth shared by up to 2 passengers.

    slot_number is 1-based per SeatInventory. RAC queue positions:
        passenger_1 → (slot_number - 1) * 2 + 1
        passenger_2 → (slot_number - 1) * 2 + 2

    SL example (7 berths → 14 passenger slots):
        slot 1 → RAC 1, RAC 2
        slot 2 → RAC 3, RAC 4  ...  slot 7 → RAC 13, RAC 14

    passenger FKs use ondelete=SET NULL so that cancelling a BookingPassengers
    row auto-clears the slot. The booking service detects the NULL and
    increments available_rac_slots on the parent SeatInventories row.
    """

    __tablename__ = "rac_slots"

    seat_inventory_id: Mapped[UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey(f"{DB_SCHEMA}.seat_inventories.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    coach_id: Mapped[UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey(f"{DB_SCHEMA}.coaches.id", ondelete="RESTRICT"),
        nullable=False,
    )
    # The physical side-lower berth (Seats.is_rac_berth = True)
    seat_id: Mapped[UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey(f"{DB_SCHEMA}.seats.id", ondelete="RESTRICT"),
        nullable=False,
    )
    # 1-based berth index within this SeatInventory
    slot_number: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    passenger_1_booking_passenger_id: Mapped[UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey(f"{DB_SCHEMA}.booking_passengers.id", ondelete="SET NULL"),
        nullable=True,
    )
    passenger_2_booking_passenger_id: Mapped[UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey(f"{DB_SCHEMA}.booking_passengers.id", ondelete="SET NULL"),
        nullable=True,
    )
    # Denormalised — avoids NULL-checking both FKs on every "find available slot" query
    is_full: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    seat_inventory = relationship("SeatInventories", back_populates="rac_slots")
    coach = relationship("Coaches")
    seat = relationship("Seats")
    passenger_1 = relationship(
        "BookingPassengers",
        foreign_keys=[passenger_1_booking_passenger_id],
        back_populates="rac_slot_as_passenger_1",
    )
    passenger_2 = relationship(
        "BookingPassengers",
        foreign_keys=[passenger_2_booking_passenger_id],
        back_populates="rac_slot_as_passenger_2",
    )

    __table_args__ = (
        # compound uniques — can't do inline
        UniqueConstraint(
            "seat_inventory_id", "slot_number", name="uq_rac_slots_inv_slot"
        ),
        UniqueConstraint("seat_inventory_id", "seat_id", name="uq_rac_slots_inv_seat"),
        # partial index — can't do inline
        Index(
            "ix_rac_slots_available",
            "seat_inventory_id",
            "slot_number",
            postgresql_where="is_full = false",
        ),
        {"schema": DB_SCHEMA},
    )

    @property
    def rac_position_passenger_1(self) -> int:
        return (self.slot_number - 1) * 2 + 1

    @property
    def rac_position_passenger_2(self) -> int:
        return (self.slot_number - 1) * 2 + 2

    @property
    def occupancy_count(self) -> int:
        return sum(
            1
            for fk in (
                self.passenger_1_booking_passenger_id,
                self.passenger_2_booking_passenger_id,
            )
            if fk is not None
        )

    def __repr__(self) -> str:
        return (
            f"<RACSlots slot={self.slot_number} "
            f"RAC{self.rac_position_passenger_1}/{self.rac_position_passenger_2} "
            f"occupancy={self.occupancy_count}/2>"
        )


# ──────────────────────────────────────────────────────────────────────────────
#  Fare Rules
# ──────────────────────────────────────────────────────────────────────────────


class FareRules(BaseModel):
    __tablename__ = "fare_rules"

    train_class: Mapped[str] = mapped_column(String(5), nullable=False, unique=True)
    base_fare_per_km: Mapped[float] = mapped_column(Float, nullable=False)
    reservation_charge: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    superfast_min_charge: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    tatkal_multiplier: Mapped[float] = mapped_column(Float, nullable=False)
    premium_tatkal_min_multiplier: Mapped[float] = mapped_column(
        Float, nullable=False, default=1.0
    )
    premium_tatkal_max_multiplier: Mapped[float] = mapped_column(
        Float, nullable=False, default=3.0
    )
    gst_percent: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    minimum_fare: Mapped[int] = mapped_column(SmallInteger, nullable=False)

    __table_args__ = ({"schema": DB_SCHEMA},)

    def __repr__(self) -> str:
        return (
            f"<FareRules class={self.train_class} "
            f"base_fare_per_km={self.base_fare_per_km} "
            f"min_fare={self.minimum_fare}>"
        )
