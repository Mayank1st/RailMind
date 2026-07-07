from datetime import datetime
from typing import Any

from app.schemas.base import BaseDTO


# -- AdminEmailLogSummary ----------------------------------------
class AdminEmailLogSummaryDTO(BaseDTO):
    email_log_id: str
    to_email: str
    subject: str
    template: str | None
    category: str
    status: str
    linked_type: str | None  # PNR | USER | TXN
    linked_label: str | None  # display ref, e.g. "8274619305"
    user_id: str | None  # navigate here when linked_type == USER
    booking_id: str | None  # navigate here when linked_type == PNR
    attempt_count: int
    queued_at: datetime | None
    sent_at: datetime | None
    failed_at: datetime | None
    created_at: datetime


# -- AdminEmailLogDetail -----------------------------------------
class AdminEmailLogDetailResponseDTO(AdminEmailLogSummaryDTO):
    provider: str | None
    provider_message_id: str | None
    context: dict[str, Any] | None  # sanitized payload (never the OTP code)
    error: str | None
    updated_at: datetime


# -- AdminEmailRetryResponse -------------------------------------
class AdminEmailRetryResponseDTO(BaseDTO):
    email_log_id: str
    category: str
    task_id: str
    attempt_count: int


# -- AdminEmailLogSummaryStats -----------------------------------
class AdminEmailLogSummaryStatsDTO(BaseDTO):
    total: int
    sent: int
    failed: int
    queued: int
    bounced: int
    templates: list[str]  # distinct template keys, to populate the filter dropdown
