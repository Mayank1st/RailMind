"""move_payment_enums_to_railmind_be_schema

Revision ID: b6c57be41a5b
Revises: 764ed4e0db6b
Create Date: 2026-06-02 09:28:24.208703

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "b6c57be41a5b"
down_revision: Union[str, None] = "764ed4e0db6b"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ── payments table: alter columns to use railmind_be.* enum types ────
    op.alter_column(
        "payments",
        "payment_method",
        existing_type=sa.Enum(
            "UPI",
            "CARD",
            "NETBANKING",
            "WALLET",
            "EMI",
            "PAY_LATER",
            "OTHER",
            name="payment_method_enum",
        ),
        type_=sa.Enum(
            "UPI",
            "CARD",
            "NETBANKING",
            "WALLET",
            "EMI",
            "PAY_LATER",
            "OTHER",
            name="payment_method_enum",
            schema="railmind_be",
        ),
        existing_nullable=True,
        postgresql_using="payment_method::text::railmind_be.payment_method_enum",
        schema="railmind_be",
    )

    op.alter_column(
        "payments",
        "payment_status",
        existing_type=sa.Enum(
            "PENDING",
            "PROCESSING",
            "SUCCESS",
            "FAILED",
            "REFUNDED",
            name="payment_status_enum",
        ),
        type_=sa.Enum(
            "PENDING",
            "PROCESSING",
            "SUCCESS",
            "FAILED",
            "REFUNDED",
            name="payment_status_enum",
            schema="railmind_be",
        ),
        existing_nullable=False,
        postgresql_using="payment_status::text::railmind_be.payment_status_enum",
        schema="railmind_be",
    )

    op.alter_column(
        "payments",
        "gateway",
        existing_type=sa.Enum(
            "RAZORPAY",
            "MOCK",
            name="payment_gateway_enum",
        ),
        type_=sa.Enum(
            "RAZORPAY",
            "MOCK",
            name="payment_gateway_enum",
            schema="railmind_be",
        ),
        existing_nullable=False,
        postgresql_using="gateway::text::railmind_be.payment_gateway_enum",
        schema="railmind_be",
    )

    # ── refunds table: alter columns to use railmind_be.* enum types ─────
    op.alter_column(
        "refunds",
        "refund_status",
        existing_type=sa.Enum(
            "INITIATED",
            "PROCESSING",
            "PROCESSED",
            "FAILED",
            "CANCELLED",
            name="refund_status_enum",
        ),
        type_=sa.Enum(
            "INITIATED",
            "PROCESSING",
            "PROCESSED",
            "FAILED",
            "CANCELLED",
            name="refund_status_enum",
            schema="railmind_be",
        ),
        existing_nullable=False,
        postgresql_using="refund_status::text::railmind_be.refund_status_enum",
        schema="railmind_be",
    )

    op.alter_column(
        "refunds",
        "refund_reason",
        existing_type=sa.Enum(
            "USER_CANCELLATION",
            "TRAIN_CANCELLED",
            "WAITLIST_DROPPED",
            "PAYMENT_DISPUTE",
            "SYSTEM_ERROR",
            "ADMIN_OVERRIDE",
            name="refund_reason_enum",
        ),
        type_=sa.Enum(
            "USER_CANCELLATION",
            "TRAIN_CANCELLED",
            "WAITLIST_DROPPED",
            "PAYMENT_DISPUTE",
            "SYSTEM_ERROR",
            "ADMIN_OVERRIDE",
            name="refund_reason_enum",
            schema="railmind_be",
        ),
        existing_nullable=False,
        postgresql_using="refund_reason::text::railmind_be.refund_reason_enum",
        schema="railmind_be",
    )

    # ── Drop orphaned public.* enums ─────────────────────────────────────
    bind = op.get_bind()

    sa.Enum(name="payment_method_enum").drop(bind, checkfirst=True)
    sa.Enum(name="payment_status_enum").drop(bind, checkfirst=True)
    sa.Enum(name="payment_gateway_enum").drop(bind, checkfirst=True)
    sa.Enum(name="refund_status_enum").drop(bind, checkfirst=True)
    sa.Enum(name="refund_reason_enum").drop(bind, checkfirst=True)


def downgrade() -> None:
    pass
