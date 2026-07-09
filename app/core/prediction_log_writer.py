import asyncio
from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.db.base import DATABASE_URL, DB_SCHEMA
from app.db.models.ai_prediction_log import AiPredictionLogs
from app.utils.logger import logger

OUTCOME_PENDING = "pending"
OUTCOME_HIT = "hit"
OUTCOME_MISS = "miss"

_INPUT_MAX = 200
_LABEL_MAX = 120

_engine = create_async_engine(
    DATABASE_URL,
    poolclass=NullPool,
    connect_args={"server_settings": {"search_path": f'"{DB_SCHEMA}"'}},
)
_session = async_sessionmaker(bind=_engine, expire_on_commit=False)

# Hold references to in-flight fire-and-forget tasks so they aren't GC'd mid-run.
_bg_tasks: set = set()


def _coerce_user_id(user_id) -> UUID | None:
    if isinstance(user_id, UUID):
        return user_id
    if isinstance(user_id, str) and user_id:
        try:
            return UUID(user_id)
        except ValueError:
            return None
    return None


async def record_prediction(
    *,
    advisor: str,
    input_summary: str,
    predicted_label: str,
    predicted_confidence: float | None = None,
    subject_ref: str | None = None,
    user_id=None,
    predicted_raw: dict | None = None,
) -> None:
    """Persist one prediction (own txn, best-effort, never raises)."""
    try:
        async with _session() as db:
            db.add(
                AiPredictionLogs(
                    advisor=advisor,
                    input_summary=(input_summary or "")[:_INPUT_MAX],
                    predicted_label=(predicted_label or "")[:_LABEL_MAX],
                    predicted_confidence=predicted_confidence,
                    subject_ref=(subject_ref or None),
                    user_id=_coerce_user_id(user_id),
                    predicted_raw=predicted_raw,
                    outcome=OUTCOME_PENDING,
                )
            )
            await db.commit()
    except Exception:
        logger.exception("prediction_log: could not record advisor=%s", advisor)


def log_prediction_async(**kwargs) -> None:
    """Fire-and-forget wrapper for the request hot path — non-blocking. Silently
    no-ops if there's no running event loop (best-effort telemetry)."""
    try:
        task = asyncio.create_task(record_prediction(**kwargs))
        _bg_tasks.add(task)
        task.add_done_callback(_bg_tasks.discard)
    except RuntimeError:
        pass


async def record_outcome(
    *,
    subject_ref: str,
    actual_label: str | None,
    outcome: str,
    advisor: str | None = None,
) -> bool:
    """Fill the actual outcome on the most recent PENDING prediction for a subject
    (best-effort; never raises). Called by the decoupled reconciler. Returns True
    if a row was updated."""
    try:
        async with _session() as db:
            query = select(AiPredictionLogs).where(
                AiPredictionLogs.subject_ref == subject_ref,
                AiPredictionLogs.outcome == OUTCOME_PENDING,
            )
            if advisor:
                query = query.where(AiPredictionLogs.advisor == advisor)
            query = query.order_by(AiPredictionLogs.created_at.desc()).limit(1)
            row = (await db.execute(query)).scalar_one_or_none()
            if row is None:
                return False
            row.actual_label = actual_label[:_LABEL_MAX] if actual_label else None
            row.outcome = outcome
            row.reconciled_at = datetime.now(timezone.utc)
            await db.commit()
            return True
    except Exception:
        logger.exception(
            "prediction_log: could not record outcome subject=%s", subject_ref
        )
        return False
