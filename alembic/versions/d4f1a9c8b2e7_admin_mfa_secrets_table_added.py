"""admin mfa secrets table added

Revision ID: d4f1a9c8b2e7
Revises: a7d2e9c4b1f6
Create Date: 2026-07-05 00:00:00.000000

Per-admin TOTP (Google Authenticator) secret for the admin-console 2FA step.
Secret is stored Fernet-encrypted; `is_enabled` flips true only after the
first 6-digit code is confirmed during setup.
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

from app.config import settings

revision: str = "d4f1a9c8b2e7"
down_revision: Union[str, None] = "a7d2e9c4b1f6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

SCHEMA = settings.DB_SCHEMA


def upgrade() -> None:
    op.create_table(
        "admin_mfa_secrets",
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("secret_encrypted", sa.Text(), nullable=False),
        sa.Column("is_enabled", sa.Boolean(), nullable=False),
        sa.Column("confirmed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_by", sa.UUID(), nullable=True),
        sa.ForeignKeyConstraint(
            ["user_id"], [f"{SCHEMA}.users.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", name="uq_admin_mfa_secrets_user_id"),
        schema=SCHEMA,
    )


def downgrade() -> None:
    op.drop_table("admin_mfa_secrets", schema=SCHEMA)
