"""error logs table added

Revision ID: a1b2c3d4e5f6
Revises: c3d4e5f6a7b8
Create Date: 2026-07-06 00:30:00.000000

Captured application errors (RM-coded business errors + 5xx crashes + DB errors)
for the admin Error Logs screen. Written best-effort from the exception handlers;
FK-free standalone records.
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

from app.config import settings

revision: str = "a1b2c3d4e5f6"
down_revision: Union[str, None] = "c3d4e5f6a7b8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

SCHEMA = settings.DB_SCHEMA


def upgrade() -> None:
    op.create_table(
        "error_logs",
        sa.Column("code", sa.String(length=40), nullable=False),
        sa.Column("domain", sa.String(length=20), nullable=True),
        sa.Column("severity", sa.String(length=20), nullable=False),
        sa.Column("status_code", sa.Integer(), nullable=False),
        sa.Column("message", sa.Text(), nullable=True),
        sa.Column("method", sa.String(length=10), nullable=True),
        sa.Column("path", sa.String(length=300), nullable=True),
        sa.Column("exception_type", sa.String(length=100), nullable=True),
        sa.Column("user_id", sa.UUID(), nullable=True),
        sa.Column("ip", sa.String(length=64), nullable=True),
        sa.Column("trace", sa.Text(), nullable=True),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_by", sa.UUID(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        schema=SCHEMA,
    )
    op.create_index("ix_error_logs_code", "error_logs", ["code"], schema=SCHEMA)
    op.create_index("ix_error_logs_domain", "error_logs", ["domain"], schema=SCHEMA)
    op.create_index("ix_error_logs_severity", "error_logs", ["severity"], schema=SCHEMA)
    op.create_index(
        "ix_error_logs_status_code", "error_logs", ["status_code"], schema=SCHEMA
    )
    op.create_index("ix_error_logs_path", "error_logs", ["path"], schema=SCHEMA)
    op.create_index("ix_error_logs_user_id", "error_logs", ["user_id"], schema=SCHEMA)
    op.create_index(
        "ix_error_logs_created_at", "error_logs", ["created_at"], schema=SCHEMA
    )


def downgrade() -> None:
    op.drop_index("ix_error_logs_created_at", table_name="error_logs", schema=SCHEMA)
    op.drop_index("ix_error_logs_user_id", table_name="error_logs", schema=SCHEMA)
    op.drop_index("ix_error_logs_path", table_name="error_logs", schema=SCHEMA)
    op.drop_index("ix_error_logs_status_code", table_name="error_logs", schema=SCHEMA)
    op.drop_index("ix_error_logs_severity", table_name="error_logs", schema=SCHEMA)
    op.drop_index("ix_error_logs_domain", table_name="error_logs", schema=SCHEMA)
    op.drop_index("ix_error_logs_code", table_name="error_logs", schema=SCHEMA)
    op.drop_table("error_logs", schema=SCHEMA)
