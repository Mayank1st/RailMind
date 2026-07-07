from sqlalchemy import ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import ARRAY, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import BaseModel, DB_SCHEMA

# ──────────────────────────────────────────────────────────────────────────────
#  ROUTES  (admin master data — corridor between two stations)
# ──────────────────────────────────────────────────────────────────────────────


class Routes(BaseModel):
    __tablename__ = "routes"

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
    corridor_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    distance_km: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # Railway zone codes the corridor passes through, e.g. ["WR", "NR"]
    zones: Mapped[list] = mapped_column(ARRAY(String), default=list, nullable=False)
    # Admin-maintained headline figure (see AdminRoutesService for the caveat)
    trains_on_route: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    source_station = relationship("Stations", foreign_keys=[source_station_id])
    destination_station = relationship(
        "Stations", foreign_keys=[destination_station_id]
    )

    __table_args__ = (
        UniqueConstraint(
            "source_station_id",
            "destination_station_id",
            name="uq_routes_source_dest",
        ),
        {"schema": DB_SCHEMA},
    )

    def __repr__(self) -> str:
        return (
            f"<Routes {self.source_station_id}->{self.destination_station_id} "
            f"{self.corridor_name}>"
        )
