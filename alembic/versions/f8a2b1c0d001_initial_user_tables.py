"""initial user tables

Revision ID: f8a2b1c0d001
Revises:
Create Date: 2026-04-03

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

from app.config import settings

revision: str = "f8a2b1c0d001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

schema = settings.DB_SCHEMA


def upgrade() -> None:
    bind = op.get_bind()

    postgresql.ENUM(
        "MALE",
        "FEMALE",
        "TRANSGENDER",
        name="gender_enum",
        schema=schema,
    ).create(bind, checkfirst=True)
    postgresql.ENUM(
        "MARRIED",
        "UNMARRIED",
        name="marital_status_enum",
        schema=schema,
    ).create(bind, checkfirst=True)
    postgresql.ENUM(
        "PASSED",
        "PENDING",
        "FAILED",
        name="kyc_status_enum",
        schema=schema,
    ).create(bind, checkfirst=True)

    op.create_table(
        "users",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("username", sa.String(length=30), nullable=False),
        sa.Column("email", sa.String(length=255), nullable=False),
        sa.Column("password", sa.String(length=255), nullable=False),
        sa.Column("is_email_verified", sa.Boolean(), nullable=False),
        sa.Column("is_mobile_verified", sa.Boolean(), nullable=False),
        sa.Column("preferred_language", sa.String(length=30), nullable=False),
        sa.Column("security_question", sa.String(length=255), nullable=False),
        sa.Column("security_answer_hash", sa.String(length=255), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        schema=schema,
    )
    op.create_index(
        "ix_users_email",
        "users",
        ["email"],
        unique=True,
        schema=schema,
    )
    op.create_index(
        "ix_users_username",
        "users",
        ["username"],
        unique=True,
        schema=schema,
    )

    op.create_table(
        "user_profiles",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("first_name", sa.String(length=50), nullable=False),
        sa.Column("last_name", sa.String(length=50), nullable=False),
        sa.Column(
            "gender",
            postgresql.ENUM(
                "MALE",
                "FEMALE",
                "TRANSGENDER",
                name="gender_enum",
                schema=schema,
                create_type=False,
            ),
            nullable=False,
        ),
        sa.Column("date_of_birth", sa.Date(), nullable=True),
        sa.Column(
            "marital_status",
            postgresql.ENUM(
                "MARRIED",
                "UNMARRIED",
                name="marital_status_enum",
                schema=schema,
                create_type=False,
            ),
            nullable=False,
        ),
        sa.Column("nationality", sa.String(length=50), nullable=True),
        sa.Column("occupation_type", sa.String(length=50), nullable=True),
        sa.Column("occupation", sa.String(length=100), nullable=True),
        sa.ForeignKeyConstraint(
            ["user_id"],
            [f"{schema}.users.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id"),
        schema=schema,
    )

    op.create_table(
        "user_contacts",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("mobile_number", sa.String(length=15), nullable=False),
        sa.Column("address_line1", sa.String(length=100), nullable=True),
        sa.Column("street", sa.String(length=100), nullable=True),
        sa.Column("state", sa.String(length=50), nullable=True),
        sa.Column("pin_code", sa.String(length=10), nullable=True),
        sa.Column("country", sa.String(length=50), nullable=True),
        sa.Column("landline_number", sa.String(length=15), nullable=True),
        sa.ForeignKeyConstraint(
            ["user_id"],
            [f"{schema}.users.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id"),
        schema=schema,
    )

    op.create_table(
        "user_kyc",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("aadhaar_number", sa.String(length=12), nullable=True),
        sa.Column("pan_number", sa.String(length=10), nullable=True),
        sa.Column(
            "kyc_status",
            postgresql.ENUM(
                "PASSED",
                "PENDING",
                "FAILED",
                name="kyc_status_enum",
                schema=schema,
                create_type=False,
            ),
            nullable=False,
            server_default=sa.text("'PENDING'"),
        ),
        sa.Column("verified_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(
            ["user_id"],
            [f"{schema}.users.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id"),
        schema=schema,
    )


def downgrade() -> None:
    op.drop_table("user_kyc", schema=schema)
    op.drop_table("user_contacts", schema=schema)
    op.drop_table("user_profiles", schema=schema)
    op.drop_index("ix_users_username", table_name="users", schema=schema)
    op.drop_index("ix_users_email", table_name="users", schema=schema)
    op.drop_table("users", schema=schema)

    for enum_name in ("kyc_status_enum", "marital_status_enum", "gender_enum"):
        op.execute(
            sa.text(f'DROP TYPE IF EXISTS "{schema}"."{enum_name}" CASCADE')
        )
