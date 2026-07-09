from datetime import date

from sqlalchemy import Boolean, Date, Index, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import DB_SCHEMA, BaseModel


class ModelVersions(BaseModel):
    __tablename__ = "model_versions"

    advisor_key: Mapped[str] = mapped_column(String(30), nullable=False, index=True)
    version_label: Mapped[str] = mapped_column(String(60), nullable=False)
    kind: Mapped[str] = mapped_column(String(20), nullable=False)  # ml | fallback
    artifact_stem: Mapped[str | None] = mapped_column(String(80), nullable=True)
    metrics: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    trained_at: Mapped[date | None] = mapped_column(Date, nullable=True)
    is_active_ml: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    __table_args__ = (
        UniqueConstraint(
            "advisor_key", "version_label", name="uq_model_versions_advisor_label"
        ),
        Index("ix_model_versions_advisor_key", "advisor_key"),
        {"schema": DB_SCHEMA},
    )

    def __repr__(self) -> str:
        return (
            f"<ModelVersions {self.advisor_key}/{self.version_label} "
            f"kind={self.kind} active_ml={self.is_active_ml}>"
        )
