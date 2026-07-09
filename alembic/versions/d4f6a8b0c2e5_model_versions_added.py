"""model versions added

Revision ID: d4f6a8b0c2e5
Revises: c3e5f7a9b1d4
Create Date: 2026-07-09 00:40:00.000000

Registered AI-model versions per advisor (AI Control → Model Versions).
Standalone config; no FK.
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from app.config import settings

revision: str = "d4f6a8b0c2e5"
down_revision: Union[str, None] = "c3e5f7a9b1d4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

SCHEMA = settings.DB_SCHEMA


def upgrade() -> None:
    op.create_table(
        "model_versions",
        sa.Column("advisor_key", sa.String(length=30), nullable=False),
        sa.Column("version_label", sa.String(length=60), nullable=False),
        sa.Column("kind", sa.String(length=20), nullable=False),
        sa.Column("artifact_stem", sa.String(length=80), nullable=True),
        sa.Column("metrics", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("trained_at", sa.Date(), nullable=True),
        sa.Column("is_active_ml", sa.Boolean(), nullable=False),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_by", sa.UUID(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "advisor_key", "version_label", name="uq_model_versions_advisor_label"
        ),
        schema=SCHEMA,
    )
    op.create_index(
        "ix_model_versions_advisor_key",
        "model_versions",
        ["advisor_key"],
        schema=SCHEMA,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_model_versions_advisor_key",
        table_name="model_versions",
        schema=SCHEMA,
    )
    op.drop_table("model_versions", schema=SCHEMA)
