# Admin Jobs — scheduled Celery/beat job observability (Tier-1 Ops).
#
# Producer: app/tasks/job_run_signals.py records every beat-job run into the
# job_runs table via Celery task_prerun/task_postrun signals. Consumer: the admin
# console (list + summary tiles + per-job run history + manual "Run now").
# JobRunStatus / JobTriggerSource enums live in constants/admin.py.

# ─── Error codes (RM-ADMIN-JOB-NNN) ───────────────────────────────────────────

ERR_JOB_NOT_FOUND = "RM-ADMIN-JOB-001"
ERR_JOB_TRIGGER_FAILED = "RM-ADMIN-JOB-002"

# ─── Celery apply_async header carrying the trigger source (best-effort) ───────

TRIGGER_HEADER_KEY = "railmind_triggered_by"

# ─── Summary window + history size ────────────────────────────────────────────

JOB_SUMMARY_WINDOW_HOURS = 24  # "Succeeded (24h)" / "Failed (24h)" tiles
JOB_RUN_HISTORY_SIZE = 20  # default run-history page size

# ─── Pretty names for the known beat jobs (fallback = humanized beat key) ──────

JOB_DISPLAY_NAMES = {
    "cleanup-search-histories-daily": "Daily search-history cleanup",
    "check-chart-preparation-due": "Chart-prep discovery",
    "compute-weekly-trending-routes": "Weekly trending refresh",
    "refresh-daily-seat-occupancy": "Daily seat-occupancy rollup",
}
