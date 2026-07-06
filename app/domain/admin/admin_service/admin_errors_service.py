import uuid

from fastapi_pagination import Params
from fastapi_pagination.bases import AbstractPage
from fastapi_pagination.ext.sqlalchemy import apaginate
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.error_log_writer import SEVERITY_ERROR, SEVERITY_WARNING
from app.core.exceptions import RailMindException
from app.db.models.error_log import ErrorLogs
from app.domain.admin.constants.admin_errors import (
    ERR_ERROR_LOG_NOT_FOUND,
    TOP_ERROR_CODES_LIMIT,
)
from app.domain.admin.dto.admin_error_logs_filter_dto import AdminErrorLogFilterDTO
from app.domain.admin.dto.admin_error_logs_response_dto import (
    AdminErrorCodeCountDTO,
    AdminErrorLogDetailResponseDTO,
    AdminErrorLogSummaryDTO,
    AdminErrorLogsSummaryStatsDTO,
)


class AdminErrorsService:
    """Read-only observability over captured RM-* errors (Tier-1 Ops)."""

    async def list_error_logs(
        self,
        db: AsyncSession,
        error_filter: AdminErrorLogFilterDTO,
        params: Params,
    ) -> AbstractPage:
        query = select(ErrorLogs)
        query = error_filter.filter(query)
        query = error_filter.sort(query)
        return await apaginate(
            db,
            query,
            params,
            transformer=lambda rows: [self._serialize_summary(row) for row in rows],
        )

    async def get_error_logs_summary(
        self, db: AsyncSession, error_filter: AdminErrorLogFilterDTO
    ) -> AdminErrorLogsSummaryStatsDTO:
        """Severity tiles + top offending codes + domain facet. Honours the
        search/code/domain/date filters but ignores severity (both buckets show)."""
        stats_filter = error_filter.model_copy(update={"severity": None})

        severity_rows = (
            await db.execute(
                stats_filter.filter(
                    select(ErrorLogs.severity, func.count(ErrorLogs.id)).group_by(
                        ErrorLogs.severity
                    )
                )
            )
        ).all()
        counts = {severity: n for severity, n in severity_rows}

        top_query = (
            stats_filter.filter(
                select(ErrorLogs.code, func.count(ErrorLogs.id).label("c")).group_by(
                    ErrorLogs.code
                )
            )
            .order_by(func.count(ErrorLogs.id).desc())
            .limit(TOP_ERROR_CODES_LIMIT)
        )
        top_rows = (await db.execute(top_query)).all()

        domain_rows = (
            await db.execute(
                stats_filter.filter(
                    select(ErrorLogs.domain)
                    .distinct()
                    .where(ErrorLogs.domain.isnot(None))
                )
            )
        ).all()

        return AdminErrorLogsSummaryStatsDTO(
            total=sum(counts.values()),
            error_count=counts.get(SEVERITY_ERROR, 0),
            warning_count=counts.get(SEVERITY_WARNING, 0),
            top_codes=[
                AdminErrorCodeCountDTO(code=code, count=count)
                for code, count in top_rows
            ],
            domains=sorted(d for (d,) in domain_rows if d),
        )

    async def get_error_log_detail(
        self, error_log_id: uuid.UUID, db: AsyncSession
    ) -> AdminErrorLogDetailResponseDTO:
        result = await db.execute(select(ErrorLogs).where(ErrorLogs.id == error_log_id))
        row = result.scalar_one_or_none()
        if row is None:
            raise RailMindException(
                code=ERR_ERROR_LOG_NOT_FOUND,
                message="Error log not found.",
                status_code=404,
            )
        return AdminErrorLogDetailResponseDTO(
            **self._serialize_summary(row).model_dump(),
            trace=row.trace,
        )

    @staticmethod
    def _serialize_summary(row: ErrorLogs) -> AdminErrorLogSummaryDTO:
        return AdminErrorLogSummaryDTO(
            error_log_id=str(row.id),
            code=row.code,
            domain=row.domain,
            severity=row.severity,
            status_code=row.status_code,
            message=row.message,
            method=row.method,
            path=row.path,
            exception_type=row.exception_type,
            user_id=str(row.user_id) if row.user_id else None,
            ip=row.ip,
            created_at=row.created_at,
        )
