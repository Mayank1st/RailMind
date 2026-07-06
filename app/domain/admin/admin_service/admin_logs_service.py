import uuid

from fastapi_pagination import Params
from fastapi_pagination.bases import AbstractPage
from fastapi_pagination.ext.sqlalchemy import apaginate
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import RailMindException
from app.db.models.email_log import EmailLogs
from app.domain.admin.constants.admin import EmailLogStatus
from app.domain.admin.constants.admin_logs import (
    EmailCategory,
    RETRIABLE_EMAIL_CATEGORIES,
    ERR_EMAIL_LOG_NOT_FOUND,
    ERR_EMAIL_NOT_RETRIABLE,
    ERR_EMAIL_RETRY_FAILED,
)
from app.domain.admin.dto.admin_email_logs_filter_dto import AdminEmailLogFilterDTO
from app.domain.admin.dto.admin_email_logs_response_dto import (
    AdminEmailLogDetailResponseDTO,
    AdminEmailLogSummaryDTO,
    AdminEmailLogSummaryStatsDTO,
    AdminEmailRetryResponseDTO,
)
from app.tasks.notification_tasks import task_send_booking_confirmation
from app.utils.logger import logger


class AdminLogsService:
    """Tier-1 log observability. v1 = email logs (list + detail + retry);
    job/error logs land here in later phases."""

    # ── Email logs ─────────────────────────────────────────────────────────

    async def list_email_logs(
        self,
        db: AsyncSession,
        email_filter: AdminEmailLogFilterDTO,
        params: Params,
    ) -> AbstractPage:
        query = select(EmailLogs)
        query = email_filter.filter(query)
        query = email_filter.sort(query)
        return await apaginate(
            db,
            query,
            params,
            transformer=lambda rows: [self._serialize_summary(row) for row in rows],
        )

    async def get_email_logs_summary(
        self, db: AsyncSession, email_filter: AdminEmailLogFilterDTO
    ) -> AdminEmailLogSummaryStatsDTO:
        """Status-breakdown pills + the template facet for the filter dropdown.
        Honours the search/template/date filters but ignores status, so the
        breakdown always shows every bucket."""
        stats_filter = email_filter.model_copy(
            update={"status": None, "status__in": None}
        )

        count_query = stats_filter.filter(
            select(EmailLogs.status, func.count(EmailLogs.id)).group_by(
                EmailLogs.status
            )
        )
        counts = {status: n for status, n in (await db.execute(count_query)).all()}

        template_query = stats_filter.filter(
            select(EmailLogs.template).distinct().where(EmailLogs.template.isnot(None))
        )
        templates = sorted(t for (t,) in (await db.execute(template_query)).all() if t)

        return AdminEmailLogSummaryStatsDTO(
            total=sum(counts.values()),
            sent=counts.get(EmailLogStatus.SENT.value, 0),
            failed=counts.get(EmailLogStatus.FAILED.value, 0),
            queued=counts.get(EmailLogStatus.QUEUED.value, 0),
            bounced=counts.get(EmailLogStatus.BOUNCED.value, 0),
            templates=templates,
        )

    async def get_email_log_detail(
        self, email_log_id: uuid.UUID, db: AsyncSession
    ) -> AdminEmailLogDetailResponseDTO:
        row = await self._get_or_raise(email_log_id, db)
        return self._serialize_detail(row)

    async def retry_email_log(
        self, email_log_id: uuid.UUID, db: AsyncSession
    ) -> AdminEmailRetryResponseDTO:
        row = await self._get_or_raise(email_log_id, db)

        # Only failed sends can be retried, and only certain categories.
        if row.status != EmailLogStatus.FAILED.value:
            raise RailMindException(
                code=ERR_EMAIL_NOT_RETRIABLE,
                message="Only failed emails can be retried.",
                status_code=422,
            )
        if row.category not in RETRIABLE_EMAIL_CATEGORIES:
            raise RailMindException(
                code=ERR_EMAIL_NOT_RETRIABLE,
                message=f"{row.category} emails can't be retried.",
                status_code=422,
            )

        task_id = self._redispatch(row)

        row.attempt_count = (row.attempt_count or 1) + 1
        await db.flush()

        logger.info(
            "Admin retried email_log id=%s category=%s task_id=%s",
            row.id,
            row.category,
            task_id,
        )
        return AdminEmailRetryResponseDTO(
            email_log_id=str(row.id),
            category=row.category,
            task_id=task_id,
            attempt_count=row.attempt_count,
        )

    # ── Helpers ────────────────────────────────────────────────────────────

    async def _get_or_raise(
        self, email_log_id: uuid.UUID, db: AsyncSession
    ) -> EmailLogs:
        result = await db.execute(select(EmailLogs).where(EmailLogs.id == email_log_id))
        row = result.scalar_one_or_none()
        if row is None:
            raise RailMindException(
                code=ERR_EMAIL_LOG_NOT_FOUND,
                message="Email log not found.",
                status_code=404,
            )
        return row

    @staticmethod
    def _redispatch(row: EmailLogs) -> str:
        """Re-enqueue the original Celery task for a retriable category. Returns
        the new task id. A fresh email_logs row records that new attempt."""
        if row.category == EmailCategory.BOOKING_CONFIRMATION.value:
            if not row.booking_id:
                raise RailMindException(
                    code=ERR_EMAIL_RETRY_FAILED,
                    message="This email has no booking reference to resend.",
                    status_code=422,
                )
            task = task_send_booking_confirmation.delay(str(row.booking_id))
            return task.id
        # Guarded by RETRIABLE_EMAIL_CATEGORIES; unreachable unless a category is
        # added to that set without a re-dispatch branch here.
        raise RailMindException(
            code=ERR_EMAIL_RETRY_FAILED,
            message=f"No retry handler for {row.category}.",
            status_code=422,
        )

    @staticmethod
    def _serialize_summary(row: EmailLogs) -> AdminEmailLogSummaryDTO:
        return AdminEmailLogSummaryDTO(
            email_log_id=str(row.id),
            to_email=row.to_email,
            subject=row.subject,
            template=row.template,
            category=row.category,
            status=row.status,
            linked_type=row.linked_type,
            linked_label=row.linked_label,
            user_id=str(row.user_id) if row.user_id else None,
            booking_id=str(row.booking_id) if row.booking_id else None,
            attempt_count=row.attempt_count,
            queued_at=row.queued_at,
            sent_at=row.sent_at,
            failed_at=row.failed_at,
            created_at=row.created_at,
        )

    def _serialize_detail(self, row: EmailLogs) -> AdminEmailLogDetailResponseDTO:
        return AdminEmailLogDetailResponseDTO(
            **self._serialize_summary(row).model_dump(),
            provider=row.provider,
            provider_message_id=row.provider_message_id,
            context=row.context,
            error=row.error,
            updated_at=row.updated_at,
        )
