"""daily seat occupancies rollup table

Revision ID: e5a1b2c3d4f6
Revises: d4f1a9c8b2e7
Create Date: 2026-07-06 00:00:00.000000

Precomputed daily seat-occupancy rollup for the admin Overview dashboard. One
row per journey_date aggregating the multi-million-row seat_inventories table,
refreshed by a celery-beat task so the endpoint never seq-scans it on a request.
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

from app.config import settings

revision: str = "e5a1b2c3d4f6"
down_revision: Union[str, None] = "d4f1a9c8b2e7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

SCHEMA = settings.DB_SCHEMA


def upgrade() -> None:
    op.create_table(
        "daily_seat_occupancies",
        sa.Column("journey_date", sa.Date(), nullable=False),
        sa.Column("total_confirmed_seats", sa.BigInteger(), nullable=False),
        sa.Column("booked_confirmed_seats", sa.BigInteger(), nullable=False),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_by", sa.UUID(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "journey_date", name="uq_daily_seat_occupancies_journey_date"
        ),
        schema=SCHEMA,
    )


def downgrade() -> None:
    op.drop_table("daily_seat_occupancies", schema=SCHEMA)
