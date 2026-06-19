"""make wl/chart timestamp columns tz-aware (timestamptz)

Revision ID: 8371706db851
Revises: 5749cac2c914
Create Date: 2026-06-19 09:44:47.582912

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "8371706db851"
down_revision: Union[str, None] = "5749cac2c914"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _alter(table, col, tz):
    # Existing naive values were written as UTC → interpret them as UTC.
    using = f"{col} AT TIME ZONE 'UTC'" if tz else f"{col} AT TIME ZONE 'UTC'"
    op.alter_column(
        table,
        col,
        type_=sa.DateTime(timezone=tz),
        existing_type=sa.DateTime(timezone=not tz),
        existing_nullable=True,
        postgresql_using=using,
        schema="railmind_be",
    )


def upgrade() -> None:
    # Align these timestamp columns with the rest of the codebase (tz-aware).
    # Fixes aware→naive write errors in _promote_wl_to_rac / chart prep.
    _alter("waitlists", "promoted_at", True)
    _alter("waitlists", "auto_cancelled_at", True)
    _alter("seat_inventories", "chart_prepared_at", True)


def downgrade() -> None:
    _alter("seat_inventories", "chart_prepared_at", False)
    _alter("waitlists", "auto_cancelled_at", False)
    _alter("waitlists", "promoted_at", False)
