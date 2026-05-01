"""Passanger's gender column size updated

Revision ID: 5207a58901b2
Revises: d1adb6832e68
Create Date: 2026-04-15 08:43:26.460336

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "5207a58901b2"
down_revision: Union[str, None] = "d1adb6832e68"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.alter_column(
        "passengers",
        "gender",
        existing_type=sa.String(length=1),
        type_=sa.String(length=10),
        nullable=False,
        schema="railmind_be",
    )


def downgrade() -> None:
    op.alter_column(
        "passengers",
        "gender",
        existing_type=sa.String(length=10),
        type_=sa.String(length=1),
        nullable=False,
        schema="railmind_be",
    )
