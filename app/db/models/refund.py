from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    DateTime,
    Enum as SAEnum,
    ForeignKey,
    Numeric,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.domain.payment.constants.payment import RefundReason, RefundStatus
from app.db.base import BaseModel, DB_SCHEMA


class Refunds(BaseModel):
    __tablename__ = "refunds"

    # ── Links to parent payment + booking ──────────────────────────────────
    payment_id: Mapped[UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey(f"{DB_SCHEMA}.payments.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    booking_id: Mapped[UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey(f"{DB_SCHEMA}.bookings.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # ── Amount breakdown ───────────────────────────────────────────────────
    refund_amount: Mapped[Decimal] = mapped_column(
        Numeric(10, 2), nullable=False
    )  # What user gets back
    deduction_amount: Mapped[Decimal] = mapped_column(
        Numeric(10, 2), default=0, nullable=False
    )  # Cancellation charges deducted
    original_amount: Mapped[Decimal] = mapped_column(
        Numeric(10, 2), nullable=False
    )  # Original payment amount (refund + deduction)
    currency: Mapped[str] = mapped_column(String(3), default="INR", nullable=False)

    # ── Status & reason ────────────────────────────────────────────────────
    refund_status: Mapped[RefundStatus] = mapped_column(
        SAEnum(RefundStatus, name="refund_status_enum", schema=DB_SCHEMA),
        default=RefundStatus.INITIATED,
        nullable=False,
        index=True,
    )
    refund_reason: Mapped[RefundReason] = mapped_column(
        SAEnum(RefundReason, name="refund_reason_enum", schema=DB_SCHEMA),
        default=RefundReason.USER_CANCELLATION,
        nullable=False,
    )
    refund_notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    # ── Gateway identifiers ────────────────────────────────────────────────
    gateway_refund_id: Mapped[str | None] = mapped_column(
        String(100), nullable=True, unique=True, index=True
    )  # Razorpay refund_id
    gateway_response: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    # ── Failure tracking ───────────────────────────────────────────────────
    failure_reason: Mapped[str | None] = mapped_column(Text, nullable=True)

    # ── Timestamps ─────────────────────────────────────────────────────────
    initiated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    processed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )  # When money actually credited back
    failed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # ── Relationships ──────────────────────────────────────────────────────
    payment = relationship("Payments", back_populates="refunds")
    booking = relationship("Bookings", back_populates="refunds")

    def __repr__(self) -> str:
        return (
            f"<Refunds id={self.id} "
            f"payment={self.payment_id} "
            f"booking={self.booking_id} "
            f"status={self.refund_status} "
            f"refund={self.refund_amount} "
            f"deduction={self.deduction_amount}>"
        )
