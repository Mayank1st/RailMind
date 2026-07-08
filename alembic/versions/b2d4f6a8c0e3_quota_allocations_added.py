"""quota allocations added

Revision ID: b2d4f6a8c0e3
Revises: a1c3e5f7b9d2
Create Date: 2026-07-08 00:30:00.000000

Admin-managed per-train, per-class quota split (Config → Quota Allocation).
`train_id` references trains.id at the app layer only — no DB FK, since trains
is owned by a different role than the migration user.
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

from app.config import settings

revision: str = "b2d4f6a8c0e3"
down_revision: Union[str, None] = "a1c3e5f7b9d2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

SCHEMA = settings.DB_SCHEMA


def upgrade() -> None:
    op.create_table(
        "quota_allocations",
        sa.Column("train_id", sa.UUID(), nullable=False),
        sa.Column("train_class", sa.String(length=5), nullable=False),
        sa.Column("general_pct", sa.SmallInteger(), nullable=False),
        sa.Column("tatkal_pct", sa.SmallInteger(), nullable=False),
        sa.Column("ladies_pct", sa.SmallInteger(), nullable=False),
        sa.Column("premium_tatkal_pct", sa.SmallInteger(), nullable=False),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_by", sa.UUID(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "train_id", "train_class", name="uq_quota_alloc_train_class"
        ),
        schema=SCHEMA,
    )
    op.create_index(
        "ix_quota_allocations_train_id",
        "quota_allocations",
        ["train_id"],
        schema=SCHEMA,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_quota_allocations_train_id",
        table_name="quota_allocations",
        schema=SCHEMA,
    )
    op.drop_table("quota_allocations", schema=SCHEMA)
