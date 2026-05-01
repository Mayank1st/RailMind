"""Base Model Timestamp Updated

Revision ID: e0ce05b3d5ed
Revises: cdee72e2d338
Create Date: 2026-04-15 09:45:06.315699

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "e0ce05b3d5ed"
down_revision: Union[str, None] = "cdee72e2d338"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
