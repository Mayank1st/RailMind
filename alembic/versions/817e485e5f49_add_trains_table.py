"""add stations, trains, train_stations

Revision ID: 817e485e5f49
Revises: 8269c9099bca
Create Date: 2026-04-05 09:44:42.012112

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect
from sqlalchemy.dialects import postgresql

from app.config import settings

revision: str = "817e485e5f49"
down_revision: Union[str, None] = "8269c9099bca"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

schema = settings.DB_SCHEMA


def upgrade() -> None:
    bind = op.get_bind()
    insp = inspect(bind)
    if insp.has_table("stations", schema=schema):
        return

    op.create_table(
        "stations",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("station_code", sa.String(length=10), nullable=False),
        sa.Column("station_name", sa.String(length=100), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("station_code"),
        schema=schema,
    )
    op.create_index(
        "ix_stations_station_code",
        "stations",
        ["station_code"],
        unique=False,
        schema=schema,
    )

    op.create_table(
        "trains",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("train_number", sa.String(length=10), nullable=False),
        sa.Column("train_name", sa.String(length=100), nullable=False),
        sa.Column("source_station_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("destination_station_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["source_station_id"],
            [f"{schema}.stations.id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["destination_station_id"],
            [f"{schema}.stations.id"],
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("train_number"),
        schema=schema,
    )
    op.create_index(
        "ix_trains_train_number",
        "trains",
        ["train_number"],
        unique=False,
        schema=schema,
    )

    op.create_table(
        "train_stations",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("train_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("station_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("sequence_number", sa.Integer(), nullable=False),
        sa.Column("arrival_time", sa.String(), nullable=True),
        sa.Column("departure_time", sa.String(), nullable=True),
        sa.Column("distance_km", sa.Integer(), nullable=False),
        sa.Column(
            "halt_minutes",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("0"),
        ),
        sa.Column(
            "is_source",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
        sa.Column(
            "is_destination",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
        sa.ForeignKeyConstraint(
            ["train_id"],
            [f"{schema}.trains.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["station_id"],
            [f"{schema}.stations.id"],
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "train_id",
            "station_id",
            name="uq_train_stations_train_station",
        ),
        schema=schema,
    )
    op.create_index(
        "ix_train_stations_train_id",
        "train_stations",
        ["train_id"],
        unique=False,
        schema=schema,
    )
    op.create_index(
        "ix_train_stations_station_id",
        "train_stations",
        ["station_id"],
        unique=False,
        schema=schema,
    )


def downgrade() -> None:
    bind = op.get_bind()
    insp = inspect(bind)
    if not insp.has_table("train_stations", schema=schema):
        return

    op.drop_index("ix_train_stations_station_id", table_name="train_stations", schema=schema)
    op.drop_index("ix_train_stations_train_id", table_name="train_stations", schema=schema)
    op.drop_table("train_stations", schema=schema)
    op.drop_index("ix_trains_train_number", table_name="trains", schema=schema)
    op.drop_table("trains", schema=schema)
    op.drop_index("ix_stations_station_code", table_name="stations", schema=schema)
    op.drop_table("stations", schema=schema)
