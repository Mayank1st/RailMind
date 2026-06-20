from __future__ import annotations

import asyncio
from collections.abc import Awaitable

from celery.utils.log import get_task_logger

from app.tasks.celery_app import celery_app

logger = get_task_logger(__name__)
_worker_loop: asyncio.AbstractEventLoop | None = None


def _run_in_worker_loop(coro: Awaitable) -> None:
    """Reuse one event loop per worker process to avoid asyncpg loop mismatch."""
    global _worker_loop
    if _worker_loop is None or _worker_loop.is_closed():
        _worker_loop = asyncio.new_event_loop()
    asyncio.set_event_loop(_worker_loop)
    _worker_loop.run_until_complete(coro)


# ── Discovery — runs every CHART_CHECK_INTERVAL_MINUTES via Celery beat ───────


async def _discover() -> tuple[int, int]:
    from app.domain.booking.constants.chart_preparation import (
        CHART_STAGE_1_WINDOW_MAX_HOURS,
        CHART_STAGE_1_WINDOW_MIN_HOURS,
        CHART_STAGE_2_WINDOW_MAX_HOURS,
        CHART_STAGE_2_WINDOW_MIN_HOURS,
        ChartStatus,
    )
    from app.db.session import async_session_local
    from app.domain.booking.booking_service.chart_preparation_service import (
        chart_preparation_service,
    )

    async with async_session_local() as db:
        stage1 = await chart_preparation_service.find_eligible_train_dates(
            db,
            min_hours=CHART_STAGE_1_WINDOW_MIN_HOURS,
            max_hours=CHART_STAGE_1_WINDOW_MAX_HOURS,
            required_status=ChartStatus.NOT_PREPARED,
        )
        stage2 = await chart_preparation_service.find_eligible_train_dates(
            db,
            min_hours=CHART_STAGE_2_WINDOW_MIN_HOURS,
            max_hours=CHART_STAGE_2_WINDOW_MAX_HOURS,
            required_status=ChartStatus.STAGE_1_PREPARED,
        )

    # Fan out per train+date (outside the session).
    for train_id, jdate in stage1:
        task_prepare_chart.delay(
            train_id=str(train_id), journey_date=jdate.isoformat(), stage=1
        )
    for train_id, jdate in stage2:
        task_prepare_chart.delay(
            train_id=str(train_id), journey_date=jdate.isoformat(), stage=2
        )

    logger.info("Chart discovery: stage1=%s stage2=%s", len(stage1), len(stage2))
    return len(stage1), len(stage2)


@celery_app.task(
    name="chart_preparation_tasks.task_check_chart_preparation_due",
    max_retries=0,
)
def task_check_chart_preparation_due() -> None:
    _run_in_worker_loop(_discover())


# ── Per train+date preparation — retryable ────────────────────────────────────


async def _prepare(train_id: str, journey_date: str, stage: int) -> None:
    from datetime import date
    from uuid import UUID

    from app.db.session import async_session_local
    from app.domain.booking.booking_service.chart_preparation_service import (
        chart_preparation_service,
    )

    async with async_session_local() as db:
        await chart_preparation_service.prepare_chart(
            db, UUID(train_id), date.fromisoformat(journey_date), stage
        )


@celery_app.task(
    name="chart_preparation_tasks.task_prepare_chart",
    bind=True,
    max_retries=3,
    default_retry_delay=60,
)
def task_prepare_chart(self, train_id: str, journey_date: str, stage: int) -> None:
    try:
        _run_in_worker_loop(_prepare(train_id, journey_date, stage))
    except Exception as e:  # noqa: BLE001
        logger.error(
            "Chart prep failed train=%s date=%s stage=%s err=%s",
            train_id,
            journey_date,
            stage,
            e,
        )
        raise self.retry(exc=e)


# ── Notification (MOCK — logs the transition; real email/push deferred) ───────


async def _notify(
    booking_passenger_id: str, old_status: str, new_status: str, stage: int
) -> None:
    logger.info(
        "[CHART NOTIFY] S%s bp=%s %s -> %s",
        stage,
        booking_passenger_id,
        old_status,
        new_status,
    )


@celery_app.task(
    name="chart_preparation_tasks.task_send_chart_notification",
    max_retries=0,
)
def task_send_chart_notification(
    booking_passenger_id: str, old_status: str, new_status: str, stage: int
) -> None:
    _run_in_worker_loop(_notify(booking_passenger_id, old_status, new_status, stage))
