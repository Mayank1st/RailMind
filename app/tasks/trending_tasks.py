from __future__ import annotations

from celery.utils.log import get_task_logger
from redis.asyncio import Redis

from app.config import settings
from app.db.session import async_session_local
from app.domain.trending.trending_service.trending_service import trending_service
from app.tasks.celery_app import celery_app
from app.tasks.worker_loop import run_in_worker_loop as _run_in_worker_loop

logger = get_task_logger(__name__)


async def _async_compute_weekly_trending() -> None:
    redis = Redis.from_url(settings.REDIS_URL, encoding="utf-8", decode_responses=True)
    try:
        # Two independent weekly snapshots — one failing must not block the other.
        try:
            async with async_session_local() as db:
                written = await trending_service.compute_weekly_trending(db, redis)
            logger.info("weekly trending computed: %s cards stored", written)
        except Exception:
            logger.exception("weekly trending routes compute failed")

        try:
            async with async_session_local() as db:
                written = await trending_service.compute_popular_destinations(db, redis)
            logger.info("popular destinations computed: %s cards stored", written)
        except Exception:
            logger.exception("popular destinations compute failed")
    finally:
        await redis.aclose()


@celery_app.task(
    name="trending_tasks.task_compute_weekly_trending",
    max_retries=0,
)
def task_compute_weekly_trending() -> None:
    _run_in_worker_loop(_async_compute_weekly_trending())
