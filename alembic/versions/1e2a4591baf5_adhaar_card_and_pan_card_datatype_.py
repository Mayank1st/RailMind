"""Adhaar card and pan card datatype changed to text

Revision ID: 1e2a4591baf5
Revises: 9ed01d783bfe
Create Date: 2026-05-30 08:49:25.376300

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "1e2a4591baf5"
down_revision: Union[str, None] = "9ed01d783bfe"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.alter_column(
        "user_kyc",
        "aadhaar_number",
        existing_type=sa.String(length=64),
        type_=sa.Text(),
        existing_nullable=True,
        schema="railmind_be",
    )
    op.alter_column(
        "user_kyc",
        "pan_number",
        existing_type=sa.String(length=64),
        type_=sa.Text(),
        existing_nullable=True,
        schema="railmind_be",
    )


def downgrade() -> None:
    op.alter_column(
        "user_kyc",
        "pan_number",
        existing_type=sa.Text(),
        type_=sa.String(length=64),
        existing_nullable=True,
        schema="railmind_be",
    )
    op.alter_column(
        "user_kyc",
        "aadhaar_number",
        existing_type=sa.Text(),
        type_=sa.String(length=64),
        existing_nullable=True,
        schema="railmind_be",
    )
