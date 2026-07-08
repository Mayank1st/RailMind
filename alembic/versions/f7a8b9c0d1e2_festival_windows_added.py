"""festival windows added

Revision ID: f7a8b9c0d1e2
Revises: e6f7a8b9c0d1
Create Date: 2026-07-07 00:10:00.000000

Admin-managed festival demand windows (Config → Holiday Calendar). Standalone
config; no FK to business tables.
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

from app.config import settings

revision: str = "f7a8b9c0d1e2"
down_revision: Union[str, None] = "e6f7a8b9c0d1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

SCHEMA = settings.DB_SCHEMA


def upgrade() -> None:
    op.create_table(
        "festival_windows",
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("festival_date", sa.Date(), nullable=False),
        sa.Column("region", sa.String(length=60), nullable=False),
        sa.Column("lookahead_days", sa.SmallInteger(), nullable=False),
        sa.Column("lookbehind_days", sa.SmallInteger(), nullable=False),
        sa.Column("demand_tier", sa.String(length=20), nullable=False),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_by", sa.UUID(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        schema=SCHEMA,
    )
    op.create_index(
        "ix_festival_windows_festival_date",
        "festival_windows",
        ["festival_date"],
        schema=SCHEMA,
    )
    op.create_index(
        "ix_festival_windows_demand_tier",
        "festival_windows",
        ["demand_tier"],
        schema=SCHEMA,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_festival_windows_demand_tier", table_name="festival_windows", schema=SCHEMA
    )
    op.drop_index(
        "ix_festival_windows_festival_date",
        table_name="festival_windows",
        schema=SCHEMA,
    )
    op.drop_table("festival_windows", schema=SCHEMA)
