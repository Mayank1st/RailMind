"""admin audit logs table added

Revision ID: c3d4e5f6a7b8
Revises: b2c3d4e5f6a7
Create Date: 2026-07-06 00:20:00.000000

Cross-cutting audit trail (plan §4.3): every sensitive admin action writes one
row here in the same transaction. FK-free — a standalone, immutable log.
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from app.config import settings

revision: str = "c3d4e5f6a7b8"
down_revision: Union[str, None] = "b2c3d4e5f6a7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

SCHEMA = settings.DB_SCHEMA


def upgrade() -> None:
    op.create_table(
        "admin_audit_logs",
        sa.Column("actor_user_id", sa.UUID(), nullable=True),
        sa.Column("actor_username", sa.String(length=50), nullable=True),
        sa.Column("action", sa.String(length=60), nullable=False),
        sa.Column("target_type", sa.String(length=30), nullable=False),
        sa.Column("target_id", sa.String(length=100), nullable=True),
        sa.Column("before", postgresql.JSONB(), nullable=True),
        sa.Column("after", postgresql.JSONB(), nullable=True),
        sa.Column("reason", sa.String(length=500), nullable=True),
        sa.Column("ip", sa.String(length=64), nullable=True),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_by", sa.UUID(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        schema=SCHEMA,
    )
    op.create_index(
        "ix_admin_audit_logs_actor_user_id",
        "admin_audit_logs",
        ["actor_user_id"],
        schema=SCHEMA,
    )
    op.create_index(
        "ix_admin_audit_logs_action", "admin_audit_logs", ["action"], schema=SCHEMA
    )
    op.create_index(
        "ix_admin_audit_logs_target_type",
        "admin_audit_logs",
        ["target_type"],
        schema=SCHEMA,
    )
    op.create_index(
        "ix_admin_audit_logs_target_id",
        "admin_audit_logs",
        ["target_id"],
        schema=SCHEMA,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_admin_audit_logs_target_id", table_name="admin_audit_logs", schema=SCHEMA
    )
    op.drop_index(
        "ix_admin_audit_logs_target_type", table_name="admin_audit_logs", schema=SCHEMA
    )
    op.drop_index(
        "ix_admin_audit_logs_action", table_name="admin_audit_logs", schema=SCHEMA
    )
    op.drop_index(
        "ix_admin_audit_logs_actor_user_id",
        table_name="admin_audit_logs",
        schema=SCHEMA,
    )
    op.drop_table("admin_audit_logs", schema=SCHEMA)
