from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.db.base import BaseModel, DB_SCHEMA
from sqlalchemy import String, Integer, ForeignKey, Boolean, UniqueConstraint, Index
from sqlalchemy.dialects.postgresql import UUID,ARRAY
from app.core.constants.train import TrainType


class Stations(BaseModel):
    __tablename__ = "stations"
    station_code: Mapped[str] = mapped_column(
        String(10), unique=True, nullable=False, index=True
    )
    station_name: Mapped[str] = mapped_column(String(100), nullable=False)

    train_stops = relationship("TrainStations", back_populates="station")


class Trains(BaseModel):
    __tablename__ = "trains"
    train_number: Mapped[str] = mapped_column(
        String(10), unique=True, nullable=False, index=True
    )
    train_name: Mapped[str] = mapped_column(String(100), nullable=False)
    train_type: Mapped[str] = mapped_column(
        String(30),
        default=TrainType.UNKNOWN,
        nullable=False,
        index=True,             
    )
    runs_on_days: Mapped[list] = mapped_column(
        ARRAY(String),          
        default=list,
        nullable=False,
        comment="Days train runs e.g. ['mon','tue','wed']"
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


class TrainStations(BaseModel):
    __tablename__ = "train_stations"
    train_id: Mapped[UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey(f"{DB_SCHEMA}.trains.id", ondelete="CASCADE"),
        nullable=False,
    )
    station_id: Mapped[UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey(f"{DB_SCHEMA}.stations.id", ondelete="RESTRICT"),
        nullable=False,
    )
    sequence_number: Mapped[int] = mapped_column(Integer, nullable=False)
    arrival_time: Mapped[str] = mapped_column(String, nullable=True)
    departure_time: Mapped[str] = mapped_column(String, nullable=True)
    distance_km: Mapped[int] = mapped_column(Integer, nullable=False)
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
        Index("ix_train_stations_train_id", "train_id"),
        Index("ix_train_stations_station_id", "station_id"),
        {"schema": DB_SCHEMA},
    )
