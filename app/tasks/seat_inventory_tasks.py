from __future__ import annotations

from celery.utils.log import get_task_logger

from app.db.session import async_session_local
from app.domain.train.train_service.seat_inventory_service import SeatInventoryService
from app.tasks.celery_app import celery_app
from app.tasks.worker_loop import run_in_worker_loop as _run_in_worker_loop

logger = get_task_logger(__name__)

_seat_inventory_service = SeatInventoryService()


async def _async_extend_seat_inventory_window() -> None:
    async with async_session_local() as db:
        inserted = await _seat_inventory_service.extend_rolling_window(db)
    logger.info("seat-inventory rolling window extended: %s rows inserted", inserted)


async def _async_prune_seat_inventory() -> None:
    async with async_session_local() as db:
        deleted = await _seat_inventory_service.prune_expired_inventory(db)
    logger.info("seat-inventory pruned: %s expired rows deleted", deleted)


@celery_app.task(
    name="seat_inventory_tasks.task_extend_seat_inventory_window",
    max_retries=0,
)
def task_extend_seat_inventory_window() -> None:
    _run_in_worker_loop(_async_extend_seat_inventory_window())


@celery_app.task(
    name="seat_inventory_tasks.task_prune_seat_inventory",
    max_retries=0,
)
def task_prune_seat_inventory() -> None:
    _run_in_worker_loop(_async_prune_seat_inventory())
