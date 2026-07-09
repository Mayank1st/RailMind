from sqlalchemy import Index, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import DB_SCHEMA, BaseModel


class LlmUsageLogs(BaseModel):
    """One LLM (Gemini / Replicate) API call (AI Control → LLM Usage).

    Written best-effort by the LLM clients at call time (latency, tokens, status).
    `status`: "ok" | "rate_limited" (provider 429) | "error". The admin screen
    rolls these up per hour (calls, tokens, 429s, fallbacks, avg latency). A
    fallback = any non-ok call (the caller degraded to a template/rule). No FK.
    """

    __tablename__ = "llm_usage_logs"

    provider: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    model: Mapped[str] = mapped_column(String(80), nullable=False)
    tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    latency_ms: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, index=True)

    __table_args__ = (
        Index("ix_llm_usage_logs_created_at", "created_at"),
        {"schema": DB_SCHEMA},
    )

    def __repr__(self) -> str:
        return (
            f"<LlmUsageLogs {self.provider}/{self.model} "
            f"status={self.status} {self.latency_ms}ms>"
        )
