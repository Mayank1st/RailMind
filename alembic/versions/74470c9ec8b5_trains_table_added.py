"""No-op: autogenerate noise (ENUM schema / index names)

Revision ID: 74470c9ec8b5
Revises: 817e485e5f49
Create Date: 2026-04-05 09:54:33.992884

Autogenerate compared PostgreSQL schema-qualified ENUM types to SQLAlchemy
``Enum`` without ``schema=`` and emitted bogus ``alter_column`` calls. Those
``ALTER TYPE`` statements used an unqualified type name and failed with
``type "kyc_status_enum" does not exist``.

The database was already correct; this revision exists only to keep revision
history linear. Safe to apply: ``upgrade`` / ``downgrade`` do nothing.

"""

from typing import Sequence, Union

revision: str = "74470c9ec8b5"
down_revision: Union[str, None] = "817e485e5f49"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
