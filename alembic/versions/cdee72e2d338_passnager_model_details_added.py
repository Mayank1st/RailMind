"""Passnager Model details added

Revision ID: cdee72e2d338
Revises: 5207a58901b2
Create Date: 2026-04-15 08:53:30.338279

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "cdee72e2d338"
down_revision: Union[str, None] = "5207a58901b2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_constraint(
        "uq_passengers_user_primary",
        "passengers",
        schema="railmind_be",
        type_="unique",
    )
    op.execute(
        "CREATE UNIQUE INDEX uix_passengers_one_primary_per_user "
        "ON railmind_be.passengers (user_id) "
        "WHERE is_primary = true"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS railmind_be.uix_passengers_one_primary_per_user")
    op.create_unique_constraint(
        "uq_passengers_user_primary",
        "passengers",
        ["user_id", "is_primary"],
        schema="railmind_be",
    )
