"""add security questions table

Revision ID: 618b65d5cef1
Revises: b2c3d4e5f002
Create Date: 2026-04-03 12:29:41.616322

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

from app.config import settings

revision: str = "618b65d5cef1"
down_revision: Union[str, None] = "b2c3d4e5f002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

schema = settings.DB_SCHEMA


def upgrade() -> None:
    op.execute(sa.text(f'CREATE SCHEMA IF NOT EXISTS "{schema}"'))

    op.create_table(
        "security_questions",
        sa.Column("question", sa.String(length=100), nullable=False),
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        schema=schema,
    )
    op.create_index(
        "ix_security_questions_question",
        "security_questions",
        ["question"],
        unique=True,
        schema=schema,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_security_questions_question",
        table_name="security_questions",
        schema=schema,
    )
    op.drop_table("security_questions", schema=schema)
