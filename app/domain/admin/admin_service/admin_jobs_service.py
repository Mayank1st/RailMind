from datetime import datetime, timedelta, timezone

from fastapi_pagination import Params
from fastapi_pagination.bases import AbstractPage
from fastapi_pagination.ext.sqlalchemy import apaginate
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import RailMindException
from app.db.models.job_run import JobRuns
from app.domain.admin.constants.admin import JobRunStatus, JobTriggerSource
from app.domain.admin.constants.admin_jobs import (
    ERR_JOB_NOT_FOUND,
    ERR_JOB_TRIGGER_FAILED,
    JOB_DISPLAY_NAMES,
    JOB_SUMMARY_WINDOW_HOURS,
    TRIGGER_HEADER_KEY,
)
from app.domain.admin.dto.admin_jobs_response_dto import (
    AdminJobRunDTO,
    AdminJobSummaryDTO,
    AdminJobsSummaryStatsDTO,
    AdminJobTriggerResponseDTO,
)
from app.tasks.celery_app import celery_app
from app.utils.logger import logger

_DOW = {
    "0": "Sun",
    "1": "Mon",
    "2": "Tue",
    "3": "Wed",
    "4": "Thu",
    "5": "Fri",
    "6": "Sat",
}


class AdminJobsService:
    """Scheduled-job observability. The job LIST comes from the Celery beat
    schedule (registry); run history/status comes from the job_runs table."""

    # ── List + summary ─────────────────────────────────────────────────────

    async def list_jobs(self, db: AsyncSession) -> list[AdminJobSummaryDTO]:
        registry = self._registry()
        latest = await self._latest_runs(db, list(registry.keys()))
        rows = []
        for job_key, meta in registry.items():
            run = latest.get(job_key)
            rows.append(
                AdminJobSummaryDTO(
                    **meta,
                    last_run_at=run.started_at if run else None,
                    last_status=run.status if run else None,
                    last_duration_ms=run.duration_ms if run else None,
                )
            )
        return rows

    async def get_jobs_summary(self, db: AsyncSession) -> AdminJobsSummaryStatsDTO:
        window_start = datetime.now(timezone.utc) - timedelta(
            hours=JOB_SUMMARY_WINDOW_HOURS
        )

        def _count(*conditions):
            return select(func.count()).select_from(JobRuns).where(*conditions)

        succeeded = await db.scalar(
            _count(
                JobRuns.status == JobRunStatus.SUCCESS.value,
                JobRuns.started_at >= window_start,
            )
        )
        failed = await db.scalar(
            _count(
                JobRuns.status == JobRunStatus.FAILED.value,
                JobRuns.started_at >= window_start,
            )
        )
        running = await db.scalar(_count(JobRuns.status == JobRunStatus.RUNNING.value))
        return AdminJobsSummaryStatsDTO(
            scheduled_jobs=len(self._registry()),
            succeeded_24h=succeeded or 0,
            running_now=running or 0,
            failed_24h=failed or 0,
        )

    async def get_job_runs(
        self, job_key: str, db: AsyncSession, params: Params
    ) -> AbstractPage:
        if job_key not in self._registry():
            raise RailMindException(
                code=ERR_JOB_NOT_FOUND,
                message="Scheduled job not found.",
                status_code=404,
            )
        query = (
            select(JobRuns)
            .where(JobRuns.job_key == job_key)
            .order_by(JobRuns.started_at.desc())
        )
        return await apaginate(
            db,
            query,
            params,
            transformer=lambda rows: [self._serialize_run(row) for row in rows],
        )

    async def trigger_job(self, job_key: str) -> AdminJobTriggerResponseDTO:
        meta = self._registry().get(job_key)
        if meta is None:
            raise RailMindException(
                code=ERR_JOB_NOT_FOUND,
                message="Scheduled job not found.",
                status_code=404,
            )
        try:
            result = celery_app.send_task(
                meta["task_name"],
                headers={TRIGGER_HEADER_KEY: JobTriggerSource.MANUAL.value},
            )
        except Exception as exc:
            logger.exception("Manual job trigger failed job_key=%s", job_key)
            raise RailMindException(
                code=ERR_JOB_TRIGGER_FAILED,
                message="Could not enqueue the job. Check the worker/broker.",
                status_code=502,
            ) from exc
        logger.info("Admin triggered job_key=%s task_id=%s", job_key, result.id)
        return AdminJobTriggerResponseDTO(
            job_key=job_key, task_id=result.id, status="QUEUED"
        )

    # ── Registry (from the Celery beat schedule) ───────────────────────────

    def _registry(self) -> dict:
        registry = {}
        for job_key, entry in celery_app.conf.beat_schedule.items():
            schedule = entry.get("schedule")
            cron_str, human = self._describe_schedule(schedule)
            registry[job_key] = {
                "job_key": job_key,
                "job_name": JOB_DISPLAY_NAMES.get(job_key, self._humanize(job_key)),
                "task_name": entry.get("task", ""),
                "schedule_cron": cron_str,
                "schedule_human": human,
                "next_run_at": self._next_run(schedule),
            }
        return registry

    async def _latest_runs(self, db: AsyncSession, job_keys: list[str]) -> dict:
        if not job_keys:
            return {}
        query = (
            select(JobRuns)
            .where(JobRuns.job_key.in_(job_keys))
            .order_by(JobRuns.job_key, JobRuns.started_at.desc())
            .distinct(JobRuns.job_key)
        )
        rows = (await db.execute(query)).scalars().all()
        return {row.job_key: row for row in rows}

    # ── Helpers ────────────────────────────────────────────────────────────

    @staticmethod
    def _humanize(job_key: str) -> str:
        return job_key.replace("-", " ").replace("_", " ").capitalize()

    @staticmethod
    def _describe_schedule(schedule) -> tuple[str, str]:
        try:
            fields = [
                str(schedule._orig_minute),
                str(schedule._orig_hour),
                str(schedule._orig_day_of_month),
                str(schedule._orig_month_of_year),
                str(schedule._orig_day_of_week),
            ]
            return " ".join(fields), AdminJobsService._humanize_cron(fields)
        except Exception:
            return str(schedule), str(schedule)

    @staticmethod
    def _humanize_cron(fields: list[str]) -> str:
        minute, hour, _dom, _mon, dow = fields
        if minute.startswith("*/") and hour == "*":
            return f"every {minute[2:]} min"
        if hour.startswith("*/"):
            return f"every {hour[2:]} h"
        if minute.isdigit() and hour.isdigit():
            hhmm = f"{int(hour):02d}:{int(minute):02d}"
            if dow != "*":
                return f"{_DOW.get(dow, dow)} {hhmm}"
            return f"{hhmm} daily"
        return " ".join(fields)

    @staticmethod
    def _next_run(schedule) -> datetime | None:
        try:
            schedule.app = celery_app
            now = schedule.now()
            nxt = now + schedule.remaining_estimate(now)
            # remaining_estimate lands ~1s under the boundary — round to the minute
            nxt = (nxt + timedelta(seconds=30)).replace(second=0, microsecond=0)
            return nxt.astimezone(timezone.utc)
        except Exception:
            return None

    @staticmethod
    def _serialize_run(row: JobRuns) -> AdminJobRunDTO:
        return AdminJobRunDTO(
            job_run_id=str(row.id),
            run_at=row.started_at,
            status=row.status,
            duration_ms=row.duration_ms,
            records=row.records,
            message=row.message,
            error=row.error,
            triggered_by=row.triggered_by,
            finished_at=row.finished_at,
        )
