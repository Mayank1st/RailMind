"""Recreate fare_rules and passengers tables

Revision ID: 84b57c23385e
Revises: e0ce05b3d5ed
Create Date: 2026-04-19 11:20:15.554278

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "84b57c23385e"
down_revision: Union[str, None] = "e0ce05b3d5ed"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ── fare_rules ────────────────────────────────────────────────────────────
    op.create_table(
        "fare_rules",
        sa.Column("train_class", sa.String(length=5), nullable=False),
        sa.Column("base_fare_per_km", sa.Float(), nullable=False),
        sa.Column("minimum_fare", sa.SmallInteger(), nullable=False),
        sa.Column("reservation_charge", sa.SmallInteger(), nullable=False),
        sa.Column("superfast_min_charge", sa.SmallInteger(), nullable=False),
        sa.Column("tatkal_multiplier", sa.Float(), nullable=False),
        sa.Column("premium_tatkal_min_multiplier", sa.Float(), nullable=False),
        sa.Column("premium_tatkal_max_multiplier", sa.Float(), nullable=False),
        sa.Column("gst_percent", sa.Float(), nullable=False),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_by", sa.UUID(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("train_class", name="uq_fare_rules_train_class"),
        schema="railmind_be",
    )

    # ── passengers ────────────────────────────────────────────────────────────
    op.create_table(
        "passengers",
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("full_name", sa.String(length=100), nullable=False),
        sa.Column("age", sa.Integer(), nullable=False),
        sa.Column("gender", sa.String(length=10), nullable=False),
        sa.Column("id_type", sa.String(length=20), nullable=True),
        sa.Column("id_number", sa.String(length=30), nullable=True),
        sa.Column("berth_preference", sa.String(length=5), nullable=False),
        sa.Column("is_primary", sa.Boolean(), nullable=False),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_by", sa.UUID(), nullable=True),
        sa.ForeignKeyConstraint(
            ["user_id"], ["railmind_be.users.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        schema="railmind_be",
    )
    op.create_index(
        "ix_passengers_user_id",
        "passengers",
        ["user_id"],
        unique=False,
        schema="railmind_be",
    )
    op.execute(
        "CREATE UNIQUE INDEX uix_passengers_one_primary_per_user "
        "ON railmind_be.passengers (user_id) "
        "WHERE is_primary = true"
    )

    # ── booking_passengers FK restore ─────────────────────────────────────────
    # Clean up orphaned rows first — test data with fake passenger_ids
    op.execute(
        """
        DELETE FROM railmind_be.bookings
        WHERE id IN (
            SELECT DISTINCT booking_id
            FROM railmind_be.booking_passengers
            WHERE passenger_id NOT IN (
                SELECT id FROM railmind_be.passengers
            )
        )
    """
    )
    op.create_foreign_key(
        "fk_booking_passengers_passenger_id",
        "booking_passengers",
        "passengers",
        ["passenger_id"],
        ["id"],
        source_schema="railmind_be",
        referent_schema="railmind_be",
        ondelete="RESTRICT",
    )


def downgrade() -> None:
    op.drop_constraint(
        "fk_booking_passengers_passenger_id",
        "booking_passengers",
        schema="railmind_be",
        type_="foreignkey",
    )
    op.execute("DROP INDEX IF EXISTS railmind_be.uix_passengers_one_primary_per_user")
    op.drop_index(
        "ix_passengers_user_id", table_name="passengers", schema="railmind_be"
    )
    op.drop_table("passengers", schema="railmind_be")
    op.drop_table("fare_rules", schema="railmind_be")
