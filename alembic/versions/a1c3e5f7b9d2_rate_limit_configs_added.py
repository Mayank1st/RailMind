"""rate limit configs added

Revision ID: a1c3e5f7b9d2
Revises: f7a8b9c0d1e2
Create Date: 2026-07-08 00:10:00.000000

Admin-managed per-endpoint request ceilings (Config → Rate Limits). Standalone
config; no FK. `endpoint` is unique (it is the limiter scope key).
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

from app.config import settings

revision: str = "a1c3e5f7b9d2"
down_revision: Union[str, None] = "f7a8b9c0d1e2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

SCHEMA = settings.DB_SCHEMA


def upgrade() -> None:
    op.create_table(
        "rate_limit_configs",
        sa.Column("endpoint", sa.String(length=120), nullable=False),
        sa.Column("scope_type", sa.String(length=20), nullable=False),
        sa.Column("window_seconds", sa.Integer(), nullable=False),
        sa.Column("request_limit", sa.Integer(), nullable=False),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_by", sa.UUID(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("endpoint", name="uq_rate_limit_configs_endpoint"),
        schema=SCHEMA,
    )
    op.create_index(
        "ix_rate_limit_configs_endpoint",
        "rate_limit_configs",
        ["endpoint"],
        schema=SCHEMA,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_rate_limit_configs_endpoint",
        table_name="rate_limit_configs",
        schema=SCHEMA,
    )
    op.drop_table("rate_limit_configs", schema=SCHEMA)
