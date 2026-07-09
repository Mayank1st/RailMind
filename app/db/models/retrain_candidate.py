from datetime import datetime

from sqlalchemy import DateTime, Float, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import BaseModel


class RetrainCandidates(BaseModel):
    __tablename__ = "retrain_candidates"

    advisor_key: Mapped[str] = mapped_column(String(30), nullable=False, index=True)
    candidate_label: Mapped[str] = mapped_column(String(60), nullable=False)
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, index=True
    )  # QUEUED | RUNNING | TRAINED | PROMOTED | REJECTED | FAILED

    # ── Requested training params ─────────────────────────────────────────────
    algorithm: Mapped[str] = mapped_column(String(30), nullable=False)
    training_window: Mapped[str] = mapped_column(String(30), nullable=False)
    validation_split: Mapped[int] = mapped_column(Integer, nullable=False)  # percent
    gate_min_precision: Mapped[float] = mapped_column(Float, nullable=False)
    gate_min_recall: Mapped[float] = mapped_column(Float, nullable=False)

    # ── Result (filled by the training runner) ────────────────────────────────
    precision: Mapped[float | None] = mapped_column(Float, nullable=True)
    recall: Mapped[float | None] = mapped_column(Float, nullable=True)
    gate_passed: Mapped[bool | None] = mapped_column(nullable=True)
    baseline_precision: Mapped[float | None] = mapped_column(Float, nullable=True)
    baseline_recall: Mapped[float | None] = mapped_column(Float, nullable=True)
    confusion: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    feature_importance: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    rows_trained: Mapped[int | None] = mapped_column(Integer, nullable=True)
    duration_seconds: Mapped[int | None] = mapped_column(Integer, nullable=True)
    artifact_stem: Mapped[str | None] = mapped_column(String(80), nullable=True)
    trained_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    error: Mapped[str | None] = mapped_column(Text, nullable=True)

    # ── Promotion ─────────────────────────────────────────────────────────────
    promoted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    promote_reason: Mapped[str | None] = mapped_column(Text, nullable=True)

    def __repr__(self) -> str:
        return (
            f"<RetrainCandidates {self.candidate_label} ({self.advisor_key}) "
            f"status={self.status} gate={self.gate_passed}>"
        )
