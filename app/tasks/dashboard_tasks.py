from __future__ import annotations

from celery.utils.log import get_task_logger

from app.db.session import async_session_local
from app.domain.admin.admin_service.admin_dashboard_service import AdminDashboardService
from app.tasks.celery_app import celery_app
from app.tasks.worker_loop import run_in_worker_loop as _run_in_worker_loop

logger = get_task_logger(__name__)

_dashboard_service = AdminDashboardService()


async def _async_refresh_daily_occupancy() -> None:
    async with async_session_local() as db:
        days = await _dashboard_service.refresh_daily_occupancy(db)
    logger.info("daily seat-occupancy rollup refreshed: %s days", days)


@celery_app.task(
    name="dashboard_tasks.task_refresh_daily_occupancy",
    max_retries=0,
)
def task_refresh_daily_occupancy() -> None:
    _run_in_worker_loop(_async_refresh_daily_occupancy())
