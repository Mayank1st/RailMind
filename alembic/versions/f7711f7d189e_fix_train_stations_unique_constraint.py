"""fix train_stations unique constraint

Revision ID: f7711f7d189e
Revises: 74470c9ec8b5
Create Date: 2026-04-05 10:11:33.893013

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "f7711f7d189e"
down_revision: Union[str, None] = "74470c9ec8b5"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ── Stations index fix ────────────────────────────────────────────────────
    op.drop_index(
        op.f("ix_stations_station_code"), table_name="stations", schema="railmind_be"
    )
    op.drop_constraint(
        op.f("stations_station_code_key"),
        "stations",
        schema="railmind_be",
        type_="unique",
    )
    op.create_index(
        op.f("ix_railmind_be_stations_station_code"),
        "stations",
        ["station_code"],
        unique=True,
        schema="railmind_be",
    )

    # ── Train stations constraint fix ─────────────────────────────────────────
    op.drop_constraint(
        op.f("uq_train_stations_train_station"),
        "train_stations",
        schema="railmind_be",
        type_="unique",
    )
    op.create_unique_constraint(
        "uq_train_stations_train_station_seq",
        "train_stations",
        ["train_id", "station_id", "sequence_number"],
        schema="railmind_be",
    )

    # ── Trains index fix ──────────────────────────────────────────────────────
    op.drop_index(
        op.f("ix_trains_train_number"), table_name="trains", schema="railmind_be"
    )
    op.drop_constraint(
        op.f("trains_train_number_key"), "trains", schema="railmind_be", type_="unique"
    )
    op.create_index(
        op.f("ix_railmind_be_trains_train_number"),
        "trains",
        ["train_number"],
        unique=True,
        schema="railmind_be",
    )

    # ❌ Removed — false positive enum alter_column for kyc_status, gender, marital_status


def downgrade() -> None:
    # ── Trains index rollback ─────────────────────────────────────────────────
    op.drop_index(
        op.f("ix_railmind_be_trains_train_number"),
        table_name="trains",
        schema="railmind_be",
    )
    op.create_unique_constraint(
        op.f("trains_train_number_key"),
        "trains",
        ["train_number"],
        schema="railmind_be",
        postgresql_nulls_not_distinct=False,
    )
    op.create_index(
        op.f("ix_trains_train_number"),
        "trains",
        ["train_number"],
        unique=False,
        schema="railmind_be",
    )

    # ── Train stations constraint rollback ────────────────────────────────────
    op.drop_constraint(
        "uq_train_stations_train_station_seq",
        "train_stations",
        schema="railmind_be",
        type_="unique",
    )
    op.create_unique_constraint(
        op.f("uq_train_stations_train_station"),
        "train_stations",
        ["train_id", "station_id"],
        schema="railmind_be",
        postgresql_nulls_not_distinct=False,
    )

    # ── Stations index rollback ───────────────────────────────────────────────
    op.drop_index(
        op.f("ix_railmind_be_stations_station_code"),
        table_name="stations",
        schema="railmind_be",
    )
    op.create_unique_constraint(
        op.f("stations_station_code_key"),
        "stations",
        ["station_code"],
        schema="railmind_be",
        postgresql_nulls_not_distinct=False,
    )
    op.create_index(
        op.f("ix_stations_station_code"),
        "stations",
        ["station_code"],
        unique=False,
        schema="railmind_be",
    )

    # ❌ Removed — false positive enum alter_column for kyc_status, gender, marital_status
