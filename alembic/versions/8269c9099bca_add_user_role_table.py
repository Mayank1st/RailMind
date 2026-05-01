"""add users.role column

Revision ID: 8269c9099bca
Revises: 618b65d5cef1
Create Date: 2026-04-04 10:48:13.915986

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect

from app.config import settings

revision: str = "8269c9099bca"
down_revision: Union[str, None] = "618b65d5cef1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

schema = settings.DB_SCHEMA


def upgrade() -> None:
    bind = op.get_bind()
    insp = inspect(bind)
    cols = {c["name"] for c in insp.get_columns("users", schema=schema)}
    if "role" not in cols:
        op.add_column(
            "users",
            sa.Column("role", sa.String(length=20), nullable=True),
            schema=schema,
        )
        op.execute(
            sa.text(f"UPDATE \"{schema}\".users SET role = 'USER' WHERE role IS NULL")
        )
        op.alter_column(
            "users",
            "role",
            existing_type=sa.String(length=20),
            nullable=False,
            schema=schema,
        )
    insp = inspect(bind)
    indexes = {ix["name"] for ix in insp.get_indexes("users", schema=schema)}
    if "ix_users_role" not in indexes:
        op.create_index(
            "ix_users_role",
            "users",
            ["role"],
            unique=False,
            schema=schema,
        )


def downgrade() -> None:
    bind = op.get_bind()
    insp = inspect(bind)
    indexes = {ix["name"] for ix in insp.get_indexes("users", schema=schema)}
    if "ix_users_role" in indexes:
        op.drop_index("ix_users_role", table_name="users", schema=schema)
    cols = {c["name"] for c in insp.get_columns("users", schema=schema)}
    if "role" in cols:
        op.drop_column("users", "role", schema=schema)
