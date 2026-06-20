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

from app.domain.payment.constants.payment import (
    PaymentGateway,
    PaymentMethod,
    PaymentStatus,
)
from app.db.base import BaseModel, DB_SCHEMA


class Payments(BaseModel):
    __tablename__ = "payments"

    # ── Booking link (multiple payments allowed per booking) ───────────────
    booking_id: Mapped[UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey(f"{DB_SCHEMA}.bookings.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # ── Amount details ─────────────────────────────────────────────────────
    amount: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), default="INR", nullable=False)

    # ── Payment method & status ────────────────────────────────────────────
    payment_method: Mapped[PaymentMethod | None] = mapped_column(
        SAEnum(PaymentMethod, name="payment_method_enum", schema=DB_SCHEMA),
        nullable=True,  # populated only after user picks (post-verify)
    )
    payment_status: Mapped[PaymentStatus] = mapped_column(
        SAEnum(PaymentStatus, name="payment_status_enum", schema=DB_SCHEMA),
        default=PaymentStatus.PENDING,
        nullable=False,
        index=True,
    )

    # ── Gateway identifiers ────────────────────────────────────────────────
    gateway: Mapped[PaymentGateway] = mapped_column(
        SAEnum(PaymentGateway, name="payment_gateway_enum", schema=DB_SCHEMA),
        default=PaymentGateway.RAZORPAY,
        nullable=False,
    )
    gateway_order_id: Mapped[str] = mapped_column(
        String(100), nullable=False, unique=True, index=True
    )  # Razorpay order_id — set at initiate
    gateway_payment_id: Mapped[str | None] = mapped_column(
        String(100), nullable=True, unique=True, index=True
    )  # Razorpay payment_id — set after user pays
    gateway_signature: Mapped[str | None] = mapped_column(
        String(255), nullable=True
    )  # HMAC signature from Razorpay — for verify audit trail

    # ── Full gateway response (JSONB for querying) ─────────────────────────
    gateway_response: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    # ── Failure tracking ───────────────────────────────────────────────────
    failure_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    failure_code: Mapped[str | None] = mapped_column(String(50), nullable=True)

    # ── Timestamps ─────────────────────────────────────────────────────────
    initiated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )  # When order was created
    paid_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )  # When payment succeeded
    failed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )  # When payment failed

    # ── Relationships ──────────────────────────────────────────────────────
    booking = relationship("Bookings", back_populates="payments")
    refunds = relationship(
        "Refunds",
        back_populates="payment",
        cascade="all, delete-orphan",
    )

    def __repr__(self) -> str:
        return (
            f"<Payments id={self.id} "
            f"booking={self.booking_id} "
            f"status={self.payment_status} "
            f"amount={self.amount} "
            f"order_id={self.gateway_order_id}>"
        )
