"""email logs table added

Revision ID: f1a2b3c4d5e6
Revises: e5a1b2c3d4f6
Create Date: 2026-07-06 00:00:00.000000

Lifecycle record for every email the system sends (QUEUED → SENT/FAILED),
written best-effort at the SMTP choke point and read by the admin console.
Metadata only — no rendered body (avoids persisting OTP codes).
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from app.config import settings

revision: str = "f1a2b3c4d5e6"
down_revision: Union[str, None] = "e5a1b2c3d4f6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

SCHEMA = settings.DB_SCHEMA


def upgrade() -> None:
    op.create_table(
        "email_logs",
        sa.Column("to_email", sa.String(length=255), nullable=False),
        sa.Column("subject", sa.String(length=500), nullable=False),
        sa.Column("template", sa.String(length=100), nullable=True),
        sa.Column("category", sa.String(length=30), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("provider", sa.String(length=100), nullable=True),
        sa.Column("provider_message_id", sa.String(length=255), nullable=True),
        sa.Column("attempt_count", sa.Integer(), nullable=False),
        sa.Column("context", postgresql.JSONB(), nullable=True),
        sa.Column("linked_type", sa.String(length=10), nullable=True),
        sa.Column("linked_label", sa.String(length=100), nullable=True),
        sa.Column("user_id", sa.UUID(), nullable=True),
        sa.Column("booking_id", sa.UUID(), nullable=True),
        sa.Column("queued_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("failed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_by", sa.UUID(), nullable=True),
        sa.ForeignKeyConstraint(
            ["user_id"], [f"{SCHEMA}.users.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(
            ["booking_id"], [f"{SCHEMA}.bookings.id"], ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id"),
        schema=SCHEMA,
    )
    op.create_index("ix_email_logs_to_email", "email_logs", ["to_email"], schema=SCHEMA)
    op.create_index("ix_email_logs_status", "email_logs", ["status"], schema=SCHEMA)
    op.create_index("ix_email_logs_user_id", "email_logs", ["user_id"], schema=SCHEMA)
    op.create_index(
        "ix_email_logs_booking_id", "email_logs", ["booking_id"], schema=SCHEMA
    )
    op.create_index(
        "ix_email_logs_created_at", "email_logs", ["created_at"], schema=SCHEMA
    )


def downgrade() -> None:
    op.drop_index("ix_email_logs_created_at", table_name="email_logs", schema=SCHEMA)
    op.drop_index("ix_email_logs_booking_id", table_name="email_logs", schema=SCHEMA)
    op.drop_index("ix_email_logs_user_id", table_name="email_logs", schema=SCHEMA)
    op.drop_index("ix_email_logs_status", table_name="email_logs", schema=SCHEMA)
    op.drop_index("ix_email_logs_to_email", table_name="email_logs", schema=SCHEMA)
    op.drop_table("email_logs", schema=SCHEMA)
