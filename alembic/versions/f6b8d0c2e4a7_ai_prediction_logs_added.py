"""ai prediction logs added

Revision ID: f6b8d0c2e4a7
Revises: e5a7c9b1d3f6
Create Date: 2026-07-09 01:40:00.000000

AI-advisor prediction telemetry (AI Control → Prediction Logs). Standalone; no FK.
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from app.config import settings

revision: str = "f6b8d0c2e4a7"
down_revision: Union[str, None] = "e5a7c9b1d3f6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

SCHEMA = settings.DB_SCHEMA


def upgrade() -> None:
    op.create_table(
        "ai_prediction_logs",
        sa.Column("advisor", sa.String(length=30), nullable=False),
        sa.Column("input_summary", sa.String(length=200), nullable=False),
        sa.Column("predicted_label", sa.String(length=120), nullable=False),
        sa.Column("predicted_confidence", sa.Float(), nullable=True),
        sa.Column("subject_ref", sa.String(length=120), nullable=True),
        sa.Column("user_id", sa.UUID(), nullable=True),
        sa.Column(
            "predicted_raw", postgresql.JSONB(astext_type=sa.Text()), nullable=True
        ),
        sa.Column("actual_label", sa.String(length=120), nullable=True),
        sa.Column("outcome", sa.String(length=20), nullable=False),
        sa.Column("reconciled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_by", sa.UUID(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        schema=SCHEMA,
    )
    op.create_index(
        "ix_ai_prediction_logs_advisor",
        "ai_prediction_logs",
        ["advisor"],
        schema=SCHEMA,
    )
    op.create_index(
        "ix_ai_prediction_logs_subject_ref",
        "ai_prediction_logs",
        ["subject_ref"],
        schema=SCHEMA,
    )
    op.create_index(
        "ix_ai_prediction_logs_outcome",
        "ai_prediction_logs",
        ["outcome"],
        schema=SCHEMA,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_ai_prediction_logs_outcome", table_name="ai_prediction_logs", schema=SCHEMA
    )
    op.drop_index(
        "ix_ai_prediction_logs_subject_ref",
        table_name="ai_prediction_logs",
        schema=SCHEMA,
    )
    op.drop_index(
        "ix_ai_prediction_logs_advisor", table_name="ai_prediction_logs", schema=SCHEMA
    )
    op.drop_table("ai_prediction_logs", schema=SCHEMA)
