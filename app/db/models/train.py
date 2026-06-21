from datetime import date, datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    SmallInteger,
    String,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import ARRAY, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import BaseModel, DB_SCHEMA
from app.domain.train.constants.train import TrainType
from app.domain.booking.constants.chart_preparation import ChartStatus


class Stations(BaseModel):
    __tablename__ = "stations"

    station_code: Mapped[str] = mapped_column(
        String(10), unique=True, nullable=False, index=True
    )
    station_name: Mapped[str] = mapped_column(String(100), nullable=False)
    city: Mapped[str] = mapped_column(String(60), nullable=False, index=True)
    state: Mapped[str] = mapped_column(String(60), nullable=False)
    zone: Mapped[str] = mapped_column(String(10), nullable=True)
    latitude: Mapped[float] = mapped_column(Float, nullable=True)
    longitude: Mapped[float] = mapped_column(Float, nullable=True)
    is_junction: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_remote_location: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False, index=True
    )

    train_stops = relationship("TrainStations", back_populates="station")

    def __repr__(self) -> str:
        return f"<Station {self.station_code} — {self.station_name}>"


class Trains(BaseModel):
    __tablename__ = "trains"

    train_number: Mapped[str] = mapped_column(
        String(10), unique=True, nullable=False, index=True
    )
    train_name: Mapped[str] = mapped_column(String(100), nullable=False)
    train_type: Mapped[str] = mapped_column(
        String(30), default=TrainType.UNKNOWN, nullable=False, index=True
    )
    runs_on_days: Mapped[list] = mapped_column(
        ARRAY(String),
        default=list,
        nullable=False,
        comment="Days train runs e.g. ['mon','tue','wed']",
    )
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

    source_station = relationship("Stations", foreign_keys=[source_station_id])
    destination_station = relationship(
        "Stations", foreign_keys=[destination_station_id]
    )
    stops = relationship(
        "TrainStations",
        back_populates="train",
        order_by="TrainStations.sequence_number",
    )
    coaches = relationship(
        "Coaches", back_populates="train", cascade="all, delete-orphan"
    )
    seat_inventories = relationship(
        "SeatInventories", back_populates="train", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<Train {self.train_number} — {self.train_name}>"


class TrainStations(BaseModel):
    __tablename__ = "train_stations"

    train_id: Mapped[UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey(f"{DB_SCHEMA}.trains.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    station_id: Mapped[UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey(f"{DB_SCHEMA}.stations.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    sequence_number: Mapped[int] = mapped_column(Integer, nullable=False)
    arrival_time: Mapped[str] = mapped_column(String, nullable=True)
    departure_time: Mapped[str] = mapped_column(String, nullable=True)
    distance_km: Mapped[int] = mapped_column(Integer, nullable=False)
    day_number: Mapped[int] = mapped_column(SmallInteger, default=1, nullable=False)
    halt_minutes: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    is_source: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_destination: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    train = relationship("Trains", back_populates="stops")
    station = relationship("Stations", back_populates="train_stops")

    __table_args__ = (
        UniqueConstraint(
            "train_id",
            "station_id",
            "sequence_number",
            name="uq_train_stations_train_station_seq",
        ),
        {"schema": DB_SCHEMA},
    )

    def __repr__(self) -> str:
        return f"<TrainStations train={self.train_id} seq={self.sequence_number}>"


class Coaches(BaseModel):
    __tablename__ = "coaches"

    train_id: Mapped[UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey(f"{DB_SCHEMA}.trains.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    coach_number: Mapped[str] = mapped_column(
        String(5),
        nullable=False,
    )
    train_class: Mapped[str] = mapped_column(String(10), nullable=False, index=True)
    total_seats: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    is_ac: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    coach_position: Mapped[int | None] = mapped_column(SmallInteger, nullable=True)

    train = relationship("Trains", back_populates="coaches")
    seats = relationship("Seats", back_populates="coach", cascade="all, delete-orphan")

    __table_args__ = (
        UniqueConstraint("train_id", "coach_number", name="uq_coaches_train_coach"),
        {"schema": DB_SCHEMA},
    )

    def __repr__(self) -> str:
        return (
            f"<Coaches {self.coach_number} ({self.train_class}) train={self.train_id}>"
        )


class Seats(BaseModel):
    __tablename__ = "seats"

    coach_id: Mapped[UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey(f"{DB_SCHEMA}.coaches.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    seat_number: Mapped[int] = mapped_column(
        SmallInteger,
        nullable=False,
    )
    berth_type: Mapped[str] = mapped_column(String(5), nullable=False)
    is_rac_berth: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    coach = relationship("Coaches", back_populates="seats")

    __table_args__ = (
        UniqueConstraint("coach_id", "seat_number", name="uq_seats_coach_seat"),
        {"schema": DB_SCHEMA},
    )

    def __repr__(self) -> str:
        tag = " [RAC]" if self.is_rac_berth else ""
        return (
            f"<Seats {self.seat_number} ({self.berth_type}){tag} coach={self.coach_id}>"
        )


class SeatInventories(BaseModel):
    __tablename__ = "seat_inventories"

    train_id: Mapped[UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey(f"{DB_SCHEMA}.trains.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    journey_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    train_class: Mapped[str] = mapped_column(String(5), nullable=False)
    quota: Mapped[str] = mapped_column(String(5), nullable=False)

    # ── Confirmed seat counters ───────────────────────────────────────────────
    total_confirmed_seats: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    available_confirmed_seats: Mapped[int] = mapped_column(SmallInteger, nullable=False)

    # ── RAC counters ──────────────────────────────────────────────────────────
    # total_rac_slots = total_rac_berths × 2 (enforced by CheckConstraint)
    total_rac_berths: Mapped[int] = mapped_column(
        SmallInteger, nullable=False, default=0
    )
    total_rac_slots: Mapped[int] = mapped_column(
        SmallInteger, nullable=False, default=0
    )
    available_rac_slots: Mapped[int] = mapped_column(
        SmallInteger, nullable=False, default=0
    )

    # ── Waitlist counters ─────────────────────────────────────────────────────
    wl_count: Mapped[int] = mapped_column(SmallInteger, nullable=False, default=0)
    wl_max: Mapped[int] = mapped_column(SmallInteger, nullable=False, default=200)

    # ── Chart lifecycle ───────────────────────────────────────────────────────
    is_chart_prepared: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False
    )
    chart_prepared_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # 2-stage chart preparation (T-8h initial, T-4h final). `is_chart_prepared`
    # is kept (set True once Stage 1 runs) so existing read-side code keeps working.
    chart_status: Mapped[str] = mapped_column(
        String(20), default=ChartStatus.NOT_PREPARED.value, nullable=False
    )
    chart_prepared_stage1_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    chart_prepared_stage2_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # ── Quota release audit ───────────────────────────────────────────────────
    quota_released_seats: Mapped[int] = mapped_column(
        SmallInteger, nullable=False, default=0
    )

    train = relationship("Trains", back_populates="seat_inventories")
    rac_slots = relationship(
        "RACSlots",
        back_populates="seat_inventory",
        cascade="all, delete-orphan",
        order_by="RACSlots.slot_number",
    )

    __table_args__ = (  # FIX: was missing entirely
        UniqueConstraint(
            "train_id",
            "journey_date",
            "train_class",
            "quota",
            name="uq_seat_inv_train_date_class_quota",
        ),
        # compound index for availability search across trains
        Index("ix_seat_inv_date_class_quota", "journey_date", "train_class", "quota"),
        # chart-prep discovery scan
        Index("ix_seat_inventories_chart_lookup", "chart_status", "journey_date"),
        # safety net — service layer must still use SELECT FOR UPDATE
        CheckConstraint(
            "available_confirmed_seats >= 0", name="ck_seat_inv_cnf_gte_zero"
        ),
        CheckConstraint(
            "available_confirmed_seats <= total_confirmed_seats",
            name="ck_seat_inv_cnf_lte_total",
        ),
        CheckConstraint("available_rac_slots >= 0", name="ck_seat_inv_rac_gte_zero"),
        CheckConstraint(
            "available_rac_slots <= total_rac_slots", name="ck_seat_inv_rac_lte_total"
        ),
        CheckConstraint("wl_count >= 0", name="ck_seat_inv_wl_gte_zero"),
        CheckConstraint("wl_count <= wl_max", name="ck_seat_inv_wl_lte_max"),
        CheckConstraint(
            "total_rac_slots = total_rac_berths * 2",
            name="ck_seat_inv_rac_slots_eq_berths_x2",
        ),
        {"schema": DB_SCHEMA},
    )

    @property
    def booking_availability(self) -> str:
        if self.available_confirmed_seats > 0:
            return "AVAILABLE"
        if self.available_rac_slots > 0:
            return "RAC"
        if self.wl_count < self.wl_max:
            return "WL"
        return "REGRET"

    @property
    def next_wl_position(self) -> int:
        return self.wl_count + 1

    def __repr__(self) -> str:
        return (
            f"<SeatInventories train={self.train_id} date={self.journey_date} "
            f"{self.train_class}/{self.quota} | "
            f"CNF={self.available_confirmed_seats} "
            f"RAC={self.available_rac_slots} "
            f"WL={self.wl_count}/{self.wl_max}>"
        )
