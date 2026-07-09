"""retrain candidates added

Revision ID: e5a7c9b1d3f6
Revises: d4f6a8b0c2e5
Create Date: 2026-07-09 01:10:00.000000

Retraining candidates (AI Control → Retrain). Standalone; no FK.
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from app.config import settings

revision: str = "e5a7c9b1d3f6"
down_revision: Union[str, None] = "d4f6a8b0c2e5"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

SCHEMA = settings.DB_SCHEMA


def upgrade() -> None:
    op.create_table(
        "retrain_candidates",
        sa.Column("advisor_key", sa.String(length=30), nullable=False),
        sa.Column("candidate_label", sa.String(length=60), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("algorithm", sa.String(length=30), nullable=False),
        sa.Column("training_window", sa.String(length=30), nullable=False),
        sa.Column("validation_split", sa.Integer(), nullable=False),
        sa.Column("gate_min_precision", sa.Float(), nullable=False),
        sa.Column("gate_min_recall", sa.Float(), nullable=False),
        sa.Column("precision", sa.Float(), nullable=True),
        sa.Column("recall", sa.Float(), nullable=True),
        sa.Column("gate_passed", sa.Boolean(), nullable=True),
        sa.Column("baseline_precision", sa.Float(), nullable=True),
        sa.Column("baseline_recall", sa.Float(), nullable=True),
        sa.Column("confusion", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column(
            "feature_importance", postgresql.JSONB(astext_type=sa.Text()), nullable=True
        ),
        sa.Column("rows_trained", sa.Integer(), nullable=True),
        sa.Column("duration_seconds", sa.Integer(), nullable=True),
        sa.Column("artifact_stem", sa.String(length=80), nullable=True),
        sa.Column("trained_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("promoted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("promote_reason", sa.Text(), nullable=True),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_by", sa.UUID(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        schema=SCHEMA,
    )
    op.create_index(
        "ix_retrain_candidates_advisor_key",
        "retrain_candidates",
        ["advisor_key"],
        schema=SCHEMA,
    )
    op.create_index(
        "ix_retrain_candidates_status",
        "retrain_candidates",
        ["status"],
        schema=SCHEMA,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_retrain_candidates_status",
        table_name="retrain_candidates",
        schema=SCHEMA,
    )
    op.drop_index(
        "ix_retrain_candidates_advisor_key",
        table_name="retrain_candidates",
        schema=SCHEMA,
    )
    op.drop_table("retrain_candidates", schema=SCHEMA)
