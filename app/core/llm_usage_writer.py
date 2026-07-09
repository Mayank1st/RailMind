"""Best-effort LLM-usage telemetry writer.

The Gemini / Replicate clients call `log_llm_call_async(...)` around each API call
— fire-and-forget (non-blocking), on a dedicated NullPool connection, and never
raising: metering must not slow down or break an LLM call.
"""

import asyncio

from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.db.base import DATABASE_URL, DB_SCHEMA
from app.db.models.llm_usage_log import LlmUsageLogs
from app.utils.logger import logger

STATUS_OK = "ok"
STATUS_RATE_LIMITED = "rate_limited"  # provider 429
STATUS_ERROR = "error"

_MODEL_MAX = 80

_engine = create_async_engine(
    DATABASE_URL,
    poolclass=NullPool,
    connect_args={"server_settings": {"search_path": f'"{DB_SCHEMA}"'}},
)
_session = async_sessionmaker(bind=_engine, expire_on_commit=False)

_bg_tasks: set = set()


async def record_llm_call(
    *,
    provider: str,
    model: str,
    latency_ms: int,
    status: str,
    tokens: int | None = None,
) -> None:
    """Persist one LLM call (own txn, best-effort, never raises)."""
    try:
        async with _session() as db:
            db.add(
                LlmUsageLogs(
                    provider=provider,
                    model=(model or "")[:_MODEL_MAX],
                    tokens=tokens,
                    latency_ms=max(int(latency_ms), 0),
                    status=status,
                )
            )
            await db.commit()
    except Exception:
        logger.exception("llm_usage: could not record provider=%s", provider)


def log_llm_call_async(**kwargs) -> None:
    """Fire-and-forget wrapper for the LLM hot path — non-blocking. No-ops if
    there's no running event loop (best-effort telemetry)."""
    try:
        task = asyncio.create_task(record_llm_call(**kwargs))
        _bg_tasks.add(task)
        task.add_done_callback(_bg_tasks.discard)
    except RuntimeError:
        pass
