import asyncio
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.db.base import DATABASE_URL, DB_SCHEMA
from app.db.models.job_run import JobRuns
from app.domain.admin.constants.admin import JobRunStatus
from app.utils.logger import logger

# Job-run writes come from Celery signal handlers (sync) in the worker process.
# A NullPool engine caches no connection, so each write binds to whatever loop
# runs it — safe regardless of the worker's loop lifecycle.
_engine = create_async_engine(
    DATABASE_URL,
    poolclass=NullPool,
    connect_args={"server_settings": {"search_path": f'"{DB_SCHEMA}"'}},
)
_session = async_sessionmaker(bind=_engine, expire_on_commit=False)

MESSAGE_MAX_LEN = 500
ERROR_MAX_LEN = 2000


def _run_blocking(coro) -> None:
    """Run an async write from a SYNC Celery signal, best-effort. Skips (and
    closes the coro) if a loop is already running — e.g. tasks executed eagerly
    inside a request — to avoid nesting run_until_complete."""
    try:
        asyncio.get_running_loop()
        coro.close()  # a loop is live here — don't touch it
        return
    except RuntimeError:
        pass
    try:
        asyncio.run(coro)
    except Exception:
        logger.exception("job_run: write failed")


async def _insert_running(
    job_key: str,
    job_name: str,
    task_name: str,
    task_id: Optional[str],
    triggered_by: str,
) -> None:
    async with _session() as db:
        db.add(
            JobRuns(
                job_key=job_key,
                job_name=job_name,
                task_name=task_name,
                task_id=task_id,
                status=JobRunStatus.RUNNING.value,
                triggered_by=triggered_by,
                started_at=datetime.now(timezone.utc),
            )
        )
        await db.commit()


async def _finalize(
    task_id: Optional[str],
    status: str,
    records: Optional[int],
    message: Optional[str],
    error: Optional[str],
) -> None:
    if not task_id:
        return
    now = datetime.now(timezone.utc)
    async with _session() as db:
        result = await db.execute(
            select(JobRuns)
            .where(JobRuns.task_id == task_id)
            .order_by(JobRuns.started_at.desc())
        )
        row = result.scalars().first()
        if row is None:
            return
        row.status = status
        row.finished_at = now
        if row.started_at is not None:
            row.duration_ms = int((now - row.started_at).total_seconds() * 1000)
        row.records = records
        row.message = message[:MESSAGE_MAX_LEN] if message else None
        row.error = error[:ERROR_MAX_LEN] if error else None
        await db.commit()


def record_run_started(
    job_key: str,
    job_name: str,
    task_name: str,
    task_id: Optional[str],
    triggered_by: str,
) -> None:
    _run_blocking(_insert_running(job_key, job_name, task_name, task_id, triggered_by))


def record_run_finished(
    task_id: Optional[str],
    status: str,
    records: Optional[int] = None,
    message: Optional[str] = None,
    error: Optional[str] = None,
) -> None:
    _run_blocking(_finalize(task_id, status, records, message, error))
