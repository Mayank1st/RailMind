"""llm usage logs added

Revision ID: a7c9e1b3d5f8
Revises: f6b8d0c2e4a7
Create Date: 2026-07-09 02:10:00.000000

LLM (Gemini/Replicate) call telemetry (AI Control → LLM Usage). Standalone; no FK.
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

from app.config import settings

revision: str = "a7c9e1b3d5f8"
down_revision: Union[str, None] = "f6b8d0c2e4a7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

SCHEMA = settings.DB_SCHEMA


def upgrade() -> None:
    op.create_table(
        "llm_usage_logs",
        sa.Column("provider", sa.String(length=20), nullable=False),
        sa.Column("model", sa.String(length=80), nullable=False),
        sa.Column("tokens", sa.Integer(), nullable=True),
        sa.Column("latency_ms", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_by", sa.UUID(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        schema=SCHEMA,
    )
    op.create_index(
        "ix_llm_usage_logs_provider", "llm_usage_logs", ["provider"], schema=SCHEMA
    )
    op.create_index(
        "ix_llm_usage_logs_status", "llm_usage_logs", ["status"], schema=SCHEMA
    )
    op.create_index(
        "ix_llm_usage_logs_created_at", "llm_usage_logs", ["created_at"], schema=SCHEMA
    )


def downgrade() -> None:
    op.drop_index(
        "ix_llm_usage_logs_created_at", table_name="llm_usage_logs", schema=SCHEMA
    )
    op.drop_index(
        "ix_llm_usage_logs_status", table_name="llm_usage_logs", schema=SCHEMA
    )
    op.drop_index(
        "ix_llm_usage_logs_provider", table_name="llm_usage_logs", schema=SCHEMA
    )
    op.drop_table("llm_usage_logs", schema=SCHEMA)
