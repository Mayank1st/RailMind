"""uppercase enum stored values (BookingStatus, TrainType, PaymentStatus, UserActionType)

Revision ID: 9f1c7a2b3e4d
Revises: 8371706db851
Create Date: 2026-06-20 00:00:00.000000

Convention change: enum stored values are now UPPERCASE strings. This migrates the
already-persisted lowercase data so existing rows keep matching the enums.

- bookings.booking_status        (VARCHAR) -> upper()
- trains.train_type              (VARCHAR) -> upper()
- user_behavior_logs.action_type (VARCHAR) -> upper()

NOT migrated: payments.payment_status is a native PG enum created via SQLAlchemy
`Enum(PaymentStatus)`, which persists the enum MEMBER NAMES (already uppercase:
PENDING/PROCESSING/SUCCESS/FAILED/REFUNDED), not the values — so the stored labels
were never lowercase and need no change.
"""

from typing import Sequence, Union

from alembic import op

from app.config import settings


revision: str = "9f1c7a2b3e4d"
down_revision: Union[str, None] = "8371706db851"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

SCHEMA = settings.DB_SCHEMA


def upgrade() -> None:
    # VARCHAR columns: each new value is exactly the uppercase of the old value.
    op.execute(f'UPDATE "{SCHEMA}".bookings SET booking_status = upper(booking_status)')
    op.execute(f'UPDATE "{SCHEMA}".trains SET train_type = upper(train_type)')
    op.execute(
        f'UPDATE "{SCHEMA}".user_behavior_logs SET action_type = upper(action_type)'
    )


def downgrade() -> None:
    op.execute(f'UPDATE "{SCHEMA}".bookings SET booking_status = lower(booking_status)')
    op.execute(f'UPDATE "{SCHEMA}".trains SET train_type = lower(train_type)')
    op.execute(
        f'UPDATE "{SCHEMA}".user_behavior_logs SET action_type = lower(action_type)'
    )
