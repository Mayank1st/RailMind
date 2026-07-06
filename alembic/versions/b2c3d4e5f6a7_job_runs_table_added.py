"""job runs table added

Revision ID: b2c3d4e5f6a7
Revises: f1a2b3c4d5e6
Create Date: 2026-07-06 00:10:00.000000

One row per scheduled Celery (beat) job execution — written best-effort by the
task_prerun/task_postrun signal hooks, read by the admin console's Job/Cron Logs
screen. No FK: a run record is standalone history.
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

from app.config import settings

revision: str = "b2c3d4e5f6a7"
down_revision: Union[str, None] = "f1a2b3c4d5e6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

SCHEMA = settings.DB_SCHEMA


def upgrade() -> None:
    op.create_table(
        "job_runs",
        sa.Column("job_key", sa.String(length=100), nullable=False),
        sa.Column("job_name", sa.String(length=150), nullable=False),
        sa.Column("task_name", sa.String(length=200), nullable=False),
        sa.Column("task_id", sa.String(length=100), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("triggered_by", sa.String(length=20), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("duration_ms", sa.Integer(), nullable=True),
        sa.Column("records", sa.Integer(), nullable=True),
        sa.Column("message", sa.String(length=500), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_by", sa.UUID(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        schema=SCHEMA,
    )
    op.create_index("ix_job_runs_job_key", "job_runs", ["job_key"], schema=SCHEMA)
    op.create_index("ix_job_runs_task_id", "job_runs", ["task_id"], schema=SCHEMA)
    op.create_index("ix_job_runs_status", "job_runs", ["status"], schema=SCHEMA)
    op.create_index("ix_job_runs_started_at", "job_runs", ["started_at"], schema=SCHEMA)


def downgrade() -> None:
    op.drop_index("ix_job_runs_started_at", table_name="job_runs", schema=SCHEMA)
    op.drop_index("ix_job_runs_status", table_name="job_runs", schema=SCHEMA)
    op.drop_index("ix_job_runs_task_id", table_name="job_runs", schema=SCHEMA)
    op.drop_index("ix_job_runs_job_key", table_name="job_runs", schema=SCHEMA)
    op.drop_table("job_runs", schema=SCHEMA)
