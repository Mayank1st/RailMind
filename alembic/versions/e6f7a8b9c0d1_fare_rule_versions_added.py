"""fare rule versions added

Revision ID: e6f7a8b9c0d1
Revises: b3d5f7a9c1e2
Create Date: 2026-07-07 00:00:00.000000

Versioned fare rules for the admin Config → Fare Rules editor. Drafts are edited
here; publishing applies a version's items to the live `fare_rules` table. No FK
to business tables — self-contained config history.
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

from app.config import settings

revision: str = "e6f7a8b9c0d1"
down_revision: Union[str, None] = "b3d5f7a9c1e2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

SCHEMA = settings.DB_SCHEMA


def upgrade() -> None:
    op.create_table(
        "fare_rule_versions",
        sa.Column("version_label", sa.String(length=50), nullable=False),
        sa.Column("effective_from", sa.Date(), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("change_note", sa.Text(), nullable=True),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_by", sa.UUID(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        schema=SCHEMA,
    )
    op.create_index(
        "ix_fare_rule_versions_status", "fare_rule_versions", ["status"], schema=SCHEMA
    )

    op.create_table(
        "fare_rule_version_items",
        sa.Column("version_id", sa.UUID(), nullable=False),
        sa.Column("train_class", sa.String(length=5), nullable=False),
        sa.Column("base_fare_per_km", sa.Float(), nullable=False),
        sa.Column("reservation_charge", sa.SmallInteger(), nullable=False),
        sa.Column("superfast_min_charge", sa.SmallInteger(), nullable=False),
        sa.Column("tatkal_multiplier", sa.Float(), nullable=False),
        sa.Column("premium_tatkal_min_multiplier", sa.Float(), nullable=False),
        sa.Column("premium_tatkal_max_multiplier", sa.Float(), nullable=False),
        sa.Column("gst_percent", sa.Float(), nullable=False),
        sa.Column("minimum_fare", sa.SmallInteger(), nullable=False),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_by", sa.UUID(), nullable=True),
        sa.ForeignKeyConstraint(
            ["version_id"],
            [f"{SCHEMA}.fare_rule_versions.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("version_id", "train_class", name="uq_fare_version_class"),
        schema=SCHEMA,
    )
    op.create_index(
        "ix_fare_rule_version_items_version_id",
        "fare_rule_version_items",
        ["version_id"],
        schema=SCHEMA,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_fare_rule_version_items_version_id",
        table_name="fare_rule_version_items",
        schema=SCHEMA,
    )
    op.drop_table("fare_rule_version_items", schema=SCHEMA)
    op.drop_index(
        "ix_fare_rule_versions_status", table_name="fare_rule_versions", schema=SCHEMA
    )
    op.drop_table("fare_rule_versions", schema=SCHEMA)
