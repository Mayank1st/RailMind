"""make gender/marital_status/mobile_number nullable for google users

Revision ID: c1f2e3d4a5b6
Revises: 9ed01d783bfe
Create Date: 2026-06-06

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

from app.config import settings

revision: str = "c1f2e3d4a5b6"
down_revision: Union[str, None] = "ba7e7b6309d3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

schema = settings.DB_SCHEMA


def upgrade() -> None:
    op.alter_column(
        "user_profiles",
        "gender",
        existing_type=postgresql.ENUM(
            "MALE", "FEMALE", "TRANSGENDER", name="gender_enum", schema=schema
        ),
        nullable=True,
        schema=schema,
    )
    op.alter_column(
        "user_profiles",
        "marital_status",
        existing_type=postgresql.ENUM(
            "MARRIED", "UNMARRIED", name="marital_status_enum", schema=schema
        ),
        nullable=True,
        schema=schema,
    )
    op.alter_column(
        "user_contacts",
        "mobile_number",
        existing_type=sa.String(length=15),
        nullable=True,
        schema=schema,
    )


def downgrade() -> None:
    op.alter_column(
        "user_contacts",
        "mobile_number",
        existing_type=sa.String(length=15),
        nullable=False,
        schema=schema,
    )
    op.alter_column(
        "user_profiles",
        "marital_status",
        existing_type=postgresql.ENUM(
            "MARRIED", "UNMARRIED", name="marital_status_enum", schema=schema
        ),
        nullable=False,
        schema=schema,
    )
    op.alter_column(
        "user_profiles",
        "gender",
        existing_type=postgresql.ENUM(
            "MALE", "FEMALE", "TRANSGENDER", name="gender_enum", schema=schema
        ),
        nullable=False,
        schema=schema,
    )
