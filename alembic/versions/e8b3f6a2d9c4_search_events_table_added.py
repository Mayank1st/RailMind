"""search events table added

Revision ID: e8b3f6a2d9c4
Revises: c4a9d1e7f2b8
Create Date: 2026-07-04 00:00:00.000000

Append-only search log for demand analytics — every /train/search lands here,
guests included (identity = user_id or salted session_hash). search_histories
stays the logged-in-only "recent searches" feature; the weekly trending job
now aggregates from this table.
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

from app.config import settings

revision: str = "e8b3f6a2d9c4"
down_revision: Union[str, None] = "c4a9d1e7f2b8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

SCHEMA = settings.DB_SCHEMA


def upgrade() -> None:
    op.create_table(
        "search_events",
        sa.Column("user_id", sa.UUID(), nullable=True),
        sa.Column("session_hash", sa.String(length=64), nullable=True),
        sa.Column("source_station_id", sa.UUID(), nullable=False),
        sa.Column("destination_station_id", sa.UUID(), nullable=False),
        sa.Column("journey_date", sa.Date(), nullable=True),
        sa.Column("train_class", sa.String(length=5), nullable=True),
        sa.Column("quota", sa.String(length=5), nullable=True),
        sa.Column("searched_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_by", sa.UUID(), nullable=True),
        sa.ForeignKeyConstraint(
            ["user_id"], [f"{SCHEMA}.users.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(
            ["source_station_id"], [f"{SCHEMA}.stations.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["destination_station_id"], [f"{SCHEMA}.stations.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        schema=SCHEMA,
    )
    op.create_index(
        "ix_search_events_searched_at",
        "search_events",
        ["searched_at"],
        unique=False,
        schema=SCHEMA,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_search_events_searched_at", table_name="search_events", schema=SCHEMA
    )
    op.drop_table("search_events", schema=SCHEMA)
