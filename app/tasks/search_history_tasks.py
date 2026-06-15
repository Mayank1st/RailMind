from __future__ import annotations

import asyncio
from collections.abc import Awaitable
from typing import Optional

from celery.utils.log import get_task_logger

from app.tasks.celery_app import celery_app

logger = get_task_logger(__name__)
_worker_loop: asyncio.AbstractEventLoop | None = None


def _run_in_worker_loop(coro: Awaitable[None]) -> None:
    """Reuse one event loop per worker process to avoid asyncpg loop mismatch."""
    global _worker_loop
    if _worker_loop is None or _worker_loop.is_closed():
        _worker_loop = asyncio.new_event_loop()
    asyncio.set_event_loop(_worker_loop)
    _worker_loop.run_until_complete(coro)


async def _async_log_search(
    user_id: str,
    from_code: str,
    to_code: str,
    journey_date: Optional[str],
    train_class: Optional[str],
    quota: Optional[str],
) -> None:
    from datetime import date

    from redis.asyncio import Redis

    from app.config import settings
    from app.db.session import async_session_local
    from app.services.search_history_service import search_history_service

    jdate = date.fromisoformat(journey_date) if journey_date else None

    redis = Redis.from_url(settings.REDIS_URL, encoding="utf-8", decode_responses=True)
    try:
        async with async_session_local() as db:
            logged = await search_history_service.log_search(
                db=db,
                redis=redis,
                user_id=user_id,
                from_code=from_code,
                to_code=to_code,
                journey_date=jdate,
                train_class=train_class,
                quota=quota,
            )
        if not logged:
            logger.info(
                "search history skipped (unknown/equal stations): %s -> %s",
                from_code,
                to_code,
            )
    finally:
        await redis.aclose()


@celery_app.task(
    name="search_history_tasks.task_log_search_history",
    max_retries=0,
)
def task_log_search_history(
    user_id: str,
    from_code: str,
    to_code: str,
    journey_date: Optional[str] = None,
    train_class: Optional[str] = None,
    quota: Optional[str] = None,
) -> None:
    # journey_date is passed as an ISO string (Celery serializes args as JSON).
    _run_in_worker_loop(
        _async_log_search(user_id, from_code, to_code, journey_date, train_class, quota)
    )


async def _async_cleanup_search_histories() -> None:
    from app.db.session import async_session_local
    from app.services.search_history_service import search_history_service

    async with async_session_local() as db:
        deleted = await search_history_service.cleanup(db)
    logger.info("search history cleanup removed %s past-dated rows", deleted)


@celery_app.task(
    name="search_history_tasks.task_cleanup_search_histories",
    max_retries=0,
)
def task_cleanup_search_histories() -> None:
    _run_in_worker_loop(_async_cleanup_search_histories())
