from uuid import UUID

from sqlalchemy import Index, SmallInteger, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import DB_SCHEMA, BaseModel


class QuotaAllocations(BaseModel):
    __tablename__ = "quota_allocations"

    train_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    train_class: Mapped[str] = mapped_column(String(5), nullable=False)

    general_pct: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    tatkal_pct: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    ladies_pct: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    premium_tatkal_pct: Mapped[int] = mapped_column(SmallInteger, nullable=False)

    __table_args__ = (
        UniqueConstraint("train_id", "train_class", name="uq_quota_alloc_train_class"),
        Index("ix_quota_allocations_train_id", "train_id"),
        {"schema": DB_SCHEMA},
    )

    def __repr__(self) -> str:
        return (
            f"<QuotaAllocations train={self.train_id} {self.train_class} "
            f"GN={self.general_pct} TQ={self.tatkal_pct} "
            f"LD={self.ladies_pct} PT={self.premium_tatkal_pct}>"
        )
