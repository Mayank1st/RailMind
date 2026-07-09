import csv
import io
from datetime import datetime, timedelta, timezone

from sqlalchemy import case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.llm_usage_writer import STATUS_ERROR, STATUS_OK, STATUS_RATE_LIMITED
from app.db.models.llm_usage_log import LlmUsageLogs
from app.domain.admin.constants.admin_llm_usage import (
    DEFAULT_USAGE_WINDOW_HOURS,
    MAX_USAGE_WINDOW_HOURS,
)
from app.domain.admin.dto.admin_llm_usage_response_dto import LlmUsageHourDTO

_EXPORT_HEADER = [
    "hour",
    "calls",
    "tokens",
    "rate_limit_429",
    "fallback",
    "avg_latency_ms",
]


class AdminLlmUsageService:
    """AI Control → LLM Usage. Rolls up llm_usage_logs per hour (calls, tokens,
    429s, fallbacks, avg latency) over a bounded recent window, and exports CSV."""

    async def hourly_usage(
        self, db: AsyncSession, hours: int = DEFAULT_USAGE_WINDOW_HOURS
    ) -> list[LlmUsageHourDTO]:
        rows = await self._rollup(db, hours)
        return [self._serialize(row) for row in rows]

    async def export_csv(
        self, db: AsyncSession, hours: int = DEFAULT_USAGE_WINDOW_HOURS
    ) -> str:
        rows = await self._rollup(db, hours)
        buffer = io.StringIO()
        writer = csv.writer(buffer)
        writer.writerow(_EXPORT_HEADER)
        for row in rows:
            item = self._serialize(row)
            writer.writerow(
                [
                    item.hour_label,
                    item.calls,
                    item.tokens,
                    item.rate_limit_429,
                    item.fallback,
                    item.avg_latency_ms,
                ]
            )
        return buffer.getvalue()

    # ── Aggregation ─────────────────────────────────────────────────────────

    @staticmethod
    async def _rollup(db: AsyncSession, hours: int):
        window = max(1, min(int(hours), MAX_USAGE_WINDOW_HOURS))
        cutoff = datetime.now(timezone.utc) - timedelta(hours=window)
        hour_col = func.date_trunc("hour", LlmUsageLogs.created_at).label("hour")

        query = (
            select(
                hour_col,
                func.count().label("calls"),
                func.coalesce(func.sum(LlmUsageLogs.tokens), 0).label("tokens"),
                func.count(case((LlmUsageLogs.status == STATUS_RATE_LIMITED, 1))).label(
                    "rate_limit_429"
                ),
                func.count(
                    case(
                        (
                            LlmUsageLogs.status.in_(
                                [STATUS_RATE_LIMITED, STATUS_ERROR]
                            ),
                            1,
                        )
                    )
                ).label("fallback"),
                func.coalesce(func.avg(LlmUsageLogs.latency_ms), 0).label(
                    "avg_latency"
                ),
            )
            .where(LlmUsageLogs.created_at >= cutoff)
            .group_by(hour_col)
            .order_by(hour_col.desc())
        )
        return (await db.execute(query)).all()

    @staticmethod
    def _serialize(row) -> LlmUsageHourDTO:
        hour_start = row.hour
        return LlmUsageHourDTO(
            hour_start=hour_start,
            hour_label=hour_start.strftime("%H:00"),
            calls=int(row.calls or 0),
            tokens=int(row.tokens or 0),
            rate_limit_429=int(row.rate_limit_429 or 0),
            fallback=int(row.fallback or 0),
            avg_latency_ms=int(round(float(row.avg_latency or 0))),
        )
