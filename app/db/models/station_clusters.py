import uuid

from sqlalchemy import ForeignKey, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import DB_SCHEMA, BaseModel


class StationClusters(BaseModel):
    __tablename__ = "station_clusters"

    cluster_code: Mapped[str] = mapped_column(
        String(20), unique=True, nullable=False
    )  # e.g. "MUMBAI", "DELHI"
    cluster_name: Mapped[str] = mapped_column(
        String(100), nullable=False
    )  # e.g. "Mumbai Metropolitan"
    primary_station_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey(f"{DB_SCHEMA}.stations.id"),
        nullable=False,
    )  # main station of the cluster (BCT for Mumbai)

    __table_args__ = ({"schema": DB_SCHEMA},)

    def __repr__(self) -> str:
        return f"<StationCluster {self.cluster_code}>"


class StationClusterMembers(BaseModel):
    __tablename__ = "station_cluster_members"

    cluster_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey(f"{DB_SCHEMA}.station_clusters.id", ondelete="CASCADE"),
        nullable=False,
    )
    station_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey(f"{DB_SCHEMA}.stations.id", ondelete="CASCADE"),
        nullable=False,
    )

    __table_args__ = (
        UniqueConstraint("cluster_id", "station_id", name="uq_cluster_station"),
        {"schema": DB_SCHEMA},
    )

    def __repr__(self) -> str:
        return f"<StationClusterMember cluster={self.cluster_id} station={self.station_id}>"
