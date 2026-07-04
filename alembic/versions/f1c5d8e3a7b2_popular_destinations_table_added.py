"""popular destinations table added

Revision ID: f1c5d8e3a7b2
Revises: e8b3f6a2d9c4
Create Date: 2026-07-04 00:00:00.000000

Weekly "Where India's heading" homepage cards — top destinations by distinct
searchers (search_events), computed Sunday 23:59 IST by the trending beat job.
Taglines are Gemini-generated with train-type fallbacks.
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

from app.config import settings

revision: str = "f1c5d8e3a7b2"
down_revision: Union[str, None] = "e8b3f6a2d9c4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

SCHEMA = settings.DB_SCHEMA


def upgrade() -> None:
    op.create_table(
        "popular_destinations",
        sa.Column("week_start", sa.Date(), nullable=False),
        sa.Column("rank", sa.Integer(), nullable=False),
        sa.Column("destination_station_id", sa.UUID(), nullable=False),
        sa.Column("destination_station_code", sa.String(length=10), nullable=False),
        sa.Column("destination_station_name", sa.String(length=100), nullable=False),
        sa.Column("origin_station_id", sa.UUID(), nullable=False),
        sa.Column("origin_station_code", sa.String(length=10), nullable=False),
        sa.Column("origin_station_name", sa.String(length=100), nullable=False),
        sa.Column("trains_count", sa.Integer(), nullable=True),
        sa.Column("train_number", sa.String(length=6), nullable=True),
        sa.Column("train_name", sa.String(length=100), nullable=True),
        sa.Column("min_fare", sa.Numeric(precision=10, scale=2), nullable=True),
        sa.Column("tagline", sa.String(length=60), nullable=True),
        sa.Column("search_count", sa.Integer(), nullable=False),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_by", sa.UUID(), nullable=True),
        sa.ForeignKeyConstraint(
            ["destination_station_id"], [f"{SCHEMA}.stations.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["origin_station_id"], [f"{SCHEMA}.stations.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("week_start", "rank", name="uq_popular_dest_week_rank"),
        schema=SCHEMA,
    )
    op.create_index(
        "ix_popular_destinations_week_start",
        "popular_destinations",
        ["week_start"],
        unique=False,
        schema=SCHEMA,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_popular_destinations_week_start",
        table_name="popular_destinations",
        schema=SCHEMA,
    )
    op.drop_table("popular_destinations", schema=SCHEMA)
