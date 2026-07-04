"""trending routes table added

Revision ID: c4a9d1e7f2b8
Revises: 9f1c7a2b3e4d
Create Date: 2026-07-04 00:00:00.000000

Weekly trending-route cards (HIGH/MEDIUM/LOW demand) computed every Sunday
23:59 IST by celery beat from the last week's search_histories.
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

from app.config import settings

revision: str = "c4a9d1e7f2b8"
down_revision: Union[str, None] = "9f1c7a2b3e4d"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

SCHEMA = settings.DB_SCHEMA


def upgrade() -> None:
    op.create_table(
        "trending_routes",
        sa.Column("week_start", sa.Date(), nullable=False),
        sa.Column("demand_level", sa.String(length=10), nullable=False),
        sa.Column("source_station_id", sa.UUID(), nullable=False),
        sa.Column("destination_station_id", sa.UUID(), nullable=False),
        sa.Column("source_station_code", sa.String(length=10), nullable=False),
        sa.Column("source_station_name", sa.String(length=100), nullable=False),
        sa.Column("destination_station_code", sa.String(length=10), nullable=False),
        sa.Column("destination_station_name", sa.String(length=100), nullable=False),
        sa.Column("train_number", sa.String(length=6), nullable=True),
        sa.Column("train_name", sa.String(length=100), nullable=True),
        sa.Column("avg_duration_minutes", sa.Integer(), nullable=True),
        sa.Column("min_fare", sa.Numeric(precision=10, scale=2), nullable=True),
        sa.Column("search_count", sa.Integer(), nullable=False),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_by", sa.UUID(), nullable=True),
        sa.ForeignKeyConstraint(
            ["source_station_id"], [f"{SCHEMA}.stations.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["destination_station_id"], [f"{SCHEMA}.stations.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "week_start", "demand_level", name="uq_trending_week_level"
        ),
        schema=SCHEMA,
    )
    op.create_index(
        "ix_trending_routes_week_start",
        "trending_routes",
        ["week_start"],
        unique=False,
        schema=SCHEMA,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_trending_routes_week_start", table_name="trending_routes", schema=SCHEMA
    )
    op.drop_table("trending_routes", schema=SCHEMA)
