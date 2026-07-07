from celery.signals import task_postrun, task_prerun

from app.domain.admin.constants.admin import JobRunStatus, JobTriggerSource
from app.domain.admin.constants.admin_jobs import JOB_DISPLAY_NAMES, TRIGGER_HEADER_KEY
from app.tasks.celery_app import celery_app
from app.tasks.job_run_writer import record_run_finished, record_run_started

_TRIGGER_VALUES = {s.value for s in JobTriggerSource}


def _humanize_key(key: str) -> str:
    return key.replace("-", " ").replace("_", " ").capitalize()


def _build_beat_index() -> dict:
    """task_name -> (job_key, job_name) for every beat-scheduled task. Only these
    are recorded; ordinary app tasks (OTP, booking, etc.) are ignored."""
    index = {}
    for key, entry in celery_app.conf.beat_schedule.items():
        task_name = entry.get("task")
        if task_name:
            index[task_name] = (key, JOB_DISPLAY_NAMES.get(key, _humanize_key(key)))
    return index


_BEAT_TASKS = _build_beat_index()


def _triggered_by(task) -> str:
    try:
        headers = getattr(task.request, "headers", None) or {}
        value = headers.get(TRIGGER_HEADER_KEY)
        if value in _TRIGGER_VALUES:
            return value
    except Exception:
        pass
    return JobTriggerSource.BEAT.value


def _extract_result(retval) -> tuple[int | None, str | None]:
    if isinstance(retval, dict):
        records = None
        for key in ("records", "count", "processed", "affected"):
            if isinstance(retval.get(key), int):
                records = retval[key]
                break
        return records, str(retval.get("message") or "OK")
    if retval is None:
        return None, "OK"
    return None, str(retval)


@task_prerun.connect
def _on_task_prerun(task_id=None, task=None, **kwargs) -> None:
    meta = _BEAT_TASKS.get(getattr(task, "name", None))
    if not meta:
        return
    job_key, job_name = meta
    record_run_started(job_key, job_name, task.name, task_id, _triggered_by(task))


@task_postrun.connect
def _on_task_postrun(
    task_id=None, task=None, retval=None, state=None, **kwargs
) -> None:
    meta = _BEAT_TASKS.get(getattr(task, "name", None))
    if not meta:
        return
    if state == "SUCCESS":
        records, message = _extract_result(retval)
        record_run_finished(task_id, JobRunStatus.SUCCESS.value, records, message, None)
    else:
        record_run_finished(
            task_id, JobRunStatus.FAILED.value, None, None, repr(retval)
        )
