from datetime import datetime

from sqlalchemy import DateTime, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import BaseModel


class JobRuns(BaseModel):
    """One row per execution of a scheduled Celery (beat) job.

    Written best-effort by app/tasks/job_run_signals.py: task_prerun inserts a
    RUNNING row keyed by the Celery task_id, task_postrun finalizes it to
    SUCCESS/FAILED with duration + result. Only beat-scheduled task names are
    recorded (not every app task). No FK — a run record outlives everything.
    """

    __tablename__ = "job_runs"

    job_key: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    job_name: Mapped[str] = mapped_column(String(150), nullable=False)
    task_name: Mapped[str] = mapped_column(String(200), nullable=False)
    task_id: Mapped[str | None] = mapped_column(String(100), nullable=True, index=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    triggered_by: Mapped[str] = mapped_column(String(20), nullable=False)
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, index=True
    )
    finished_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    records: Mapped[int | None] = mapped_column(Integer, nullable=True)
    message: Mapped[str | None] = mapped_column(String(500), nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)

    def __repr__(self) -> str:
        return (
            f"<JobRuns id={self.id} job={self.job_key} "
            f"status={self.status} task_id={self.task_id}>"
        )
