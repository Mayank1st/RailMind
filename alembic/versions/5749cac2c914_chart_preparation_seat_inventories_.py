"""chart preparation: seat_inventories chart_status + stage timestamps, widen passenger_status

Revision ID: 5749cac2c914
Revises: ae53d1730e55
Create Date: 2026-06-19 09:26:55.988969

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "5749cac2c914"
down_revision: Union[str, None] = "ae53d1730e55"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # chart_status: add NOT NULL with a server_default so existing rows backfill,
    # then drop the default (the app sets it explicitly going forward).
    op.add_column(
        "seat_inventories",
        sa.Column(
            "chart_status",
            sa.String(length=20),
            nullable=False,
            server_default="NOT_PREPARED",
        ),
        schema="railmind_be",
    )
    op.add_column(
        "seat_inventories",
        sa.Column(
            "chart_prepared_stage1_at", sa.DateTime(timezone=True), nullable=True
        ),
        schema="railmind_be",
    )
    op.add_column(
        "seat_inventories",
        sa.Column(
            "chart_prepared_stage2_at", sa.DateTime(timezone=True), nullable=True
        ),
        schema="railmind_be",
    )

    # Backfill: rows already chart-prepared (legacy boolean) → FINAL_PREPARED.
    op.execute(
        "UPDATE railmind_be.seat_inventories "
        "SET chart_status = 'FINAL_PREPARED' WHERE is_chart_prepared = true"
    )
    op.alter_column(
        "seat_inventories", "chart_status", server_default=None, schema="railmind_be"
    )

    op.create_index(
        "ix_seat_inventories_chart_lookup",
        "seat_inventories",
        ["chart_status", "journey_date"],
        unique=False,
        schema="railmind_be",
    )

    # Widen passenger_status (CNF/RAC/WL/CAN → also AUTO_CANCELLED_CHART).
    # Not auto-detected because env.py runs with compare_type=False.
    op.alter_column(
        "booking_passengers",
        "passenger_status",
        existing_type=sa.String(length=5),
        type_=sa.String(length=20),
        existing_nullable=False,
        schema="railmind_be",
    )


def downgrade() -> None:
    op.alter_column(
        "booking_passengers",
        "passenger_status",
        existing_type=sa.String(length=20),
        type_=sa.String(length=5),
        existing_nullable=False,
        schema="railmind_be",
    )
    op.drop_index(
        "ix_seat_inventories_chart_lookup",
        table_name="seat_inventories",
        schema="railmind_be",
    )
    op.drop_column("seat_inventories", "chart_prepared_stage2_at", schema="railmind_be")
    op.drop_column("seat_inventories", "chart_prepared_stage1_at", schema="railmind_be")
    op.drop_column("seat_inventories", "chart_status", schema="railmind_be")
