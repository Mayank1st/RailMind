from celery import Celery
from celery.schedules import crontab

from app.config import settings
from app.domain.booking.constants.chart_preparation import CHART_CHECK_INTERVAL_MINUTES
from app.domain.trending.constants.trending import (
    TRENDING_RUN_DAY_OF_WEEK,
    TRENDING_RUN_HOUR,
    TRENDING_RUN_MINUTE,
)


def _redis_broker_url() -> str:
    """Celery's implicit default broker is amqp://localhost — require explicit Redis URL."""
    url = (settings.REDIS_URL or "").strip()
    if not url:
        url = "redis://127.0.0.1:6379/0"
    if not url.startswith("redis://"):
        raise ValueError(
            "REDIS_URL must start with redis:// (e.g. redis://127.0.0.1:6379/0)."
        )
    # Avoid macOS ::1 vs 127.0.0.1 quirks when Redis only listens on IPv4
    return url.replace("redis://localhost", "redis://127.0.0.1", 1)


_broker = _redis_broker_url()

celery_app = Celery(
    "railmind",
    broker=_broker,
    backend=_broker,
)

celery_app.conf.update(
    broker_url=_broker,
    result_backend=_broker,
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    broker_connection_retry_on_startup=True,
    task_always_eager=settings.CELERY_TASK_ALWAYS_EAGER,
    task_eager_propagates=settings.CELERY_TASK_ALWAYS_EAGER,
    timezone="Asia/Kolkata",  # beat crontabs below are IST wall-clock times
)

# Periodic jobs — only fire when a `celery beat` process is running.
celery_app.conf.beat_schedule = {
    "cleanup-search-histories-daily": {
        "task": "search_history_tasks.task_cleanup_search_histories",
        "schedule": crontab(hour=3, minute=0),  # 03:00 daily
    },
    "check-chart-preparation-due": {
        "task": "chart_preparation_tasks.task_check_chart_preparation_due",
        "schedule": crontab(minute=f"*/{CHART_CHECK_INTERVAL_MINUTES}"),
    },
    "compute-weekly-trending-routes": {
        "task": "trending_tasks.task_compute_weekly_trending",
        "schedule": crontab(
            hour=TRENDING_RUN_HOUR,
            minute=TRENDING_RUN_MINUTE,
            day_of_week=TRENDING_RUN_DAY_OF_WEEK,
        ),  # Sunday 23:59 IST
    },
}


def _register_task_modules() -> None:
    """Import after `celery_app` exists so @celery_app.task binds to this app (not
    amqp default). The task modules import `celery_app` from this module, so these
    are the one structural exception to the top-level-imports rule."""
    import app.tasks.notification_tasks  # noqa: F401  # naming: ignore
    import app.tasks.booking_tasks  # noqa: F401  # naming: ignore
    import app.tasks.ai_tasks  # noqa: F401  # naming: ignore
    import app.tasks.booking_retry_tasks  # noqa: F401  # naming: ignore
    import app.tasks.search_history_tasks  # noqa: F401  # naming: ignore
    import app.tasks.chart_preparation_tasks  # noqa: F401  # naming: ignore
    import app.tasks.trending_tasks  # noqa: F401  # naming: ignore


_register_task_modules()
