"""notification templates added

Revision ID: b8d0f2c4e6a9
Revises: a7c9e1b3d5f8
Create Date: 2026-07-09 02:40:00.000000

Admin-managed email/SMS message templates (Config → Notification Templates).
Standalone config; no FK. `template_key` is unique.
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

from app.config import settings

revision: str = "b8d0f2c4e6a9"
down_revision: Union[str, None] = "a7c9e1b3d5f8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

SCHEMA = settings.DB_SCHEMA


def upgrade() -> None:
    op.create_table(
        "notification_templates",
        sa.Column("template_key", sa.String(length=60), nullable=False),
        sa.Column("channel", sa.String(length=10), nullable=False),
        sa.Column("subject", sa.String(length=200), nullable=True),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=10), nullable=False),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_by", sa.UUID(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("template_key", name="uq_notification_templates_key"),
        schema=SCHEMA,
    )
    op.create_index(
        "ix_notification_templates_template_key",
        "notification_templates",
        ["template_key"],
        schema=SCHEMA,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_notification_templates_template_key",
        table_name="notification_templates",
        schema=SCHEMA,
    )
    op.drop_table("notification_templates", schema=SCHEMA)
