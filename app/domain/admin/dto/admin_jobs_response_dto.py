from datetime import datetime

from app.schemas.base import BaseDTO


# -- AdminJobSummary (one list row) ------------------------------
class AdminJobSummaryDTO(BaseDTO):
    job_key: str  # beat-schedule key — used for /runs and /trigger
    job_name: str  # JOB column
    task_name: str
    schedule_cron: str  # "0 3 * * *"
    schedule_human: str  # "03:00 daily" — shown in parens
    last_run_at: datetime | None  # LAST RUN
    last_status: str | None  # STATUS — RUNNING/SUCCESS/FAILED (null = never run)
    last_duration_ms: int | None  # DURATION
    next_run_at: datetime | None  # NEXT RUN


# -- AdminJobRun (one run-history row) ---------------------------
class AdminJobRunDTO(BaseDTO):
    job_run_id: str
    run_at: datetime  # started_at — RUN AT
    status: str
    duration_ms: int | None
    records: int | None
    message: str | None
    error: str | None
    triggered_by: str
    finished_at: datetime | None


# -- AdminJobsSummaryStats (the 4 stat tiles) --------------------
class AdminJobsSummaryStatsDTO(BaseDTO):
    scheduled_jobs: int
    succeeded_24h: int
    running_now: int
    failed_24h: int


# -- AdminJobTriggerResponse -------------------------------------
class AdminJobTriggerResponseDTO(BaseDTO):
    job_key: str
    task_id: str
    status: str  # "QUEUED"
