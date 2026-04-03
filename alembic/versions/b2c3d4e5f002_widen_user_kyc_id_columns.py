"""widen user_kyc aadhaar/pan columns for HMAC storage

Revision ID: b2c3d4e5f002
Revises: f8a2b1c0d001
Create Date: 2026-04-03

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

from app.config import settings

revision: str = "b2c3d4e5f002"
down_revision: Union[str, None] = "f8a2b1c0d001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

schema = settings.DB_SCHEMA


def upgrade() -> None:
    # Raw ALTER is reliable for schema names with special chars (e.g. railmind-be).
    op.execute(
        sa.text(
            f'ALTER TABLE "{schema}".user_kyc '
            f"ALTER COLUMN aadhaar_number TYPE VARCHAR(64)"
        )
    )
    op.execute(
        sa.text(
            f'ALTER TABLE "{schema}".user_kyc '
            f"ALTER COLUMN pan_number TYPE VARCHAR(64)"
        )
    )


def downgrade() -> None:
    op.execute(
        sa.text(
            f'ALTER TABLE "{schema}".user_kyc '
            f"ALTER COLUMN pan_number TYPE VARCHAR(10)"
        )
    )
    op.execute(
        sa.text(
            f'ALTER TABLE "{schema}".user_kyc '
            f"ALTER COLUMN aadhaar_number TYPE VARCHAR(12)"
        )
    )
