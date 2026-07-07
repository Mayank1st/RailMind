from datetime import datetime

from app.schemas.base import BaseDTO


# -- AdminErrorLogSummary (one list row — no trace) --------------
class AdminErrorLogSummaryDTO(BaseDTO):
    error_log_id: str
    code: str  # RM-BKG-001
    domain: str | None  # BKG
    severity: str  # ERROR | WARNING
    status_code: int
    message: str | None
    method: str | None
    path: str | None
    exception_type: str | None
    user_id: str | None
    ip: str | None
    created_at: datetime


# -- AdminErrorLogDetail (drawer — adds traceback) ---------------
class AdminErrorLogDetailResponseDTO(AdminErrorLogSummaryDTO):
    trace: str | None  # server-side traceback (5xx only; null for 4xx)


# -- AdminErrorCodeCount (top-offenders row) ---------------------
class AdminErrorCodeCountDTO(BaseDTO):
    code: str
    count: int


# -- AdminErrorLogsSummaryStats (tiles + facets) ----------------
class AdminErrorLogsSummaryStatsDTO(BaseDTO):
    total: int
    error_count: int  # severity == ERROR (5xx)
    warning_count: int  # severity == WARNING (4xx)
    top_codes: list[AdminErrorCodeCountDTO]  # most frequent codes
    domains: list[str]  # distinct domains, for the filter dropdown
