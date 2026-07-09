"""advisor toggles added

Revision ID: c3e5f7a9b1d4
Revises: b2d4f6a8c0e3
Create Date: 2026-07-09 00:10:00.000000

Admin-managed AI-advisor feature flags (AI Control → Advisor Toggles). One row
per advisor; standalone config, no FK.
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

from app.config import settings

revision: str = "c3e5f7a9b1d4"
down_revision: Union[str, None] = "b2d4f6a8c0e3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

SCHEMA = settings.DB_SCHEMA


def upgrade() -> None:
    op.create_table(
        "advisor_toggles",
        sa.Column("advisor_key", sa.String(length=30), nullable=False),
        sa.Column("state", sa.String(length=20), nullable=False),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_by", sa.UUID(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("advisor_key", name="uq_advisor_toggles_key"),
        schema=SCHEMA,
    )
    op.create_index(
        "ix_advisor_toggles_advisor_key",
        "advisor_toggles",
        ["advisor_key"],
        schema=SCHEMA,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_advisor_toggles_advisor_key",
        table_name="advisor_toggles",
        schema=SCHEMA,
    )
    op.drop_table("advisor_toggles", schema=SCHEMA)
