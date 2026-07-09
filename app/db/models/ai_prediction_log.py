from datetime import datetime
from uuid import UUID

from sqlalchemy import DateTime, Float, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import BaseModel


class AiPredictionLogs(BaseModel):
    __tablename__ = "ai_prediction_logs"

    advisor: Mapped[str] = mapped_column(String(30), nullable=False, index=True)
    input_summary: Mapped[str] = mapped_column(String(200), nullable=False)
    predicted_label: Mapped[str] = mapped_column(String(120), nullable=False)
    predicted_confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    subject_ref: Mapped[str | None] = mapped_column(
        String(120), nullable=True, index=True
    )
    user_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True), nullable=True)
    predicted_raw: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    actual_label: Mapped[str | None] = mapped_column(String(120), nullable=True)
    outcome: Mapped[str] = mapped_column(
        String(20), nullable=False, index=True
    )  # pending | hit | miss
    reconciled_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    def __repr__(self) -> str:
        return (
            f"<AiPredictionLogs {self.advisor} {self.predicted_label} "
            f"outcome={self.outcome}>"
        )
