from datetime import date, datetime

from sqlalchemy import (
    Date,
    DateTime,
    Float,
    ForeignKey,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import BaseModel, DB_SCHEMA


class FareRuleVersions(BaseModel):
    __tablename__ = "fare_rule_versions"

    version_label: Mapped[str] = mapped_column(String(50), nullable=False)
    effective_from: Mapped[date] = mapped_column(Date, nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    change_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    published_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    items = relationship(
        "FareRuleVersionItems",
        back_populates="version",
        cascade="all, delete-orphan",
        lazy="selectin",
    )

    def __repr__(self) -> str:
        return (
            f"<FareRuleVersions id={self.id} label={self.version_label} "
            f"status={self.status} effective={self.effective_from}>"
        )


class FareRuleVersionItems(BaseModel):
    """One class's fare rule within a version — mirrors every `fare_rules` field
    so a version is a complete, editable snapshot."""

    __tablename__ = "fare_rule_version_items"
    __table_args__ = (
        UniqueConstraint("version_id", "train_class", name="uq_fare_version_class"),
        {"schema": DB_SCHEMA},
    )

    version_id: Mapped[UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey(f"{DB_SCHEMA}.fare_rule_versions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    train_class: Mapped[str] = mapped_column(String(5), nullable=False)
    base_fare_per_km: Mapped[float] = mapped_column(Float, nullable=False)
    reservation_charge: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    superfast_min_charge: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    tatkal_multiplier: Mapped[float] = mapped_column(Float, nullable=False)
    premium_tatkal_min_multiplier: Mapped[float] = mapped_column(
        Float, nullable=False, default=1.0
    )
    premium_tatkal_max_multiplier: Mapped[float] = mapped_column(
        Float, nullable=False, default=3.0
    )
    gst_percent: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    minimum_fare: Mapped[int] = mapped_column(SmallInteger, nullable=False)

    version = relationship("FareRuleVersions", back_populates="items")

    def __repr__(self) -> str:
        return (
            f"<FareRuleVersionItems version={self.version_id} "
            f"class={self.train_class}>"
        )
