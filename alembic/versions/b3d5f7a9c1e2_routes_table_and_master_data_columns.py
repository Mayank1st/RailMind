"""routes table + trains/stations master-data columns

Revision ID: b3d5f7a9c1e2
Revises: a1b2c3d4e5f6
Create Date: 2026-07-07 12:00:00.000000

Admin Entities → Trains / Routes / Stations (master-data CRUD). Adds:
- a new `routes` table (corridor between two stations, admin-managed);
- trains.{distance_km, halts, classes_offered, pantry_car, is_paused};
- stations.{platforms, is_operational}.

`is_paused` (trains) and `is_operational` (stations) are the panel's status
toggles; the existing BaseModel `is_active` is reused as the soft-delete flag.
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from app.config import settings

revision: str = "b3d5f7a9c1e2"
down_revision: Union[str, None] = "a1b2c3d4e5f6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

SCHEMA = settings.DB_SCHEMA


def upgrade() -> None:
    # ── routes ────────────────────────────────────────────────────────────────
    op.create_table(
        "routes",
        sa.Column("source_station_id", sa.UUID(), nullable=False),
        sa.Column("destination_station_id", sa.UUID(), nullable=False),
        sa.Column("corridor_name", sa.String(length=100), nullable=True),
        sa.Column("distance_km", sa.Integer(), nullable=True),
        sa.Column(
            "zones",
            postgresql.ARRAY(sa.String()),
            server_default=sa.text("'{}'::varchar[]"),
            nullable=False,
        ),
        sa.Column(
            "trains_on_route",
            sa.Integer(),
            server_default=sa.text("0"),
            nullable=False,
        ),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_by", sa.UUID(), nullable=True),
        sa.ForeignKeyConstraint(
            ["source_station_id"],
            [f"{SCHEMA}.stations.id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["destination_station_id"],
            [f"{SCHEMA}.stations.id"],
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "source_station_id",
            "destination_station_id",
            name="uq_routes_source_dest",
        ),
        schema=SCHEMA,
    )
    op.create_index(
        "ix_routes_source_station_id", "routes", ["source_station_id"], schema=SCHEMA
    )
    op.create_index(
        "ix_routes_destination_station_id",
        "routes",
        ["destination_station_id"],
        schema=SCHEMA,
    )

    # ── trains ────────────────────────────────────────────────────────────────
    op.add_column(
        "trains", sa.Column("distance_km", sa.Integer(), nullable=True), schema=SCHEMA
    )
    op.add_column(
        "trains",
        sa.Column(
            "halts", sa.SmallInteger(), server_default=sa.text("0"), nullable=False
        ),
        schema=SCHEMA,
    )
    op.add_column(
        "trains",
        sa.Column(
            "classes_offered",
            postgresql.ARRAY(sa.String()),
            server_default=sa.text("'{}'::varchar[]"),
            nullable=False,
        ),
        schema=SCHEMA,
    )
    op.add_column(
        "trains",
        sa.Column(
            "pantry_car", sa.Boolean(), server_default=sa.false(), nullable=False
        ),
        schema=SCHEMA,
    )
    op.add_column(
        "trains",
        sa.Column("is_paused", sa.Boolean(), server_default=sa.false(), nullable=False),
        schema=SCHEMA,
    )

    # ── stations ──────────────────────────────────────────────────────────────
    op.add_column(
        "stations",
        sa.Column("platforms", sa.SmallInteger(), nullable=True),
        schema=SCHEMA,
    )
    op.add_column(
        "stations",
        sa.Column(
            "is_operational", sa.Boolean(), server_default=sa.true(), nullable=False
        ),
        schema=SCHEMA,
    )


def downgrade() -> None:
    op.drop_column("stations", "is_operational", schema=SCHEMA)
    op.drop_column("stations", "platforms", schema=SCHEMA)

    op.drop_column("trains", "is_paused", schema=SCHEMA)
    op.drop_column("trains", "pantry_car", schema=SCHEMA)
    op.drop_column("trains", "classes_offered", schema=SCHEMA)
    op.drop_column("trains", "halts", schema=SCHEMA)
    op.drop_column("trains", "distance_km", schema=SCHEMA)

    op.drop_index(
        "ix_routes_destination_station_id", table_name="routes", schema=SCHEMA
    )
    op.drop_index("ix_routes_source_station_id", table_name="routes", schema=SCHEMA)
    op.drop_table("routes", schema=SCHEMA)
