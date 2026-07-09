import csv
import io

from fastapi_pagination import Params
from fastapi_pagination.bases import AbstractPage
from fastapi_pagination.ext.sqlalchemy import apaginate
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.ai_prediction_log import AiPredictionLogs
from app.domain.admin.constants.admin_prediction_logs import (
    PREDICTION_EXPORT_MAX_ROWS,
)
from app.domain.admin.dto.admin_prediction_logs_filter_dto import (
    AdminPredictionLogFilterDTO,
)
from app.domain.admin.dto.admin_prediction_logs_response_dto import (
    PredictionLogItemDTO,
)

_EXPORT_HEADER = [
    "time",
    "advisor",
    "input",
    "predicted",
    "confidence",
    "actual",
    "match",
]


class AdminPredictionLogsService:
    """AI Control → Prediction Logs (read side). Lists the advisor prediction
    telemetry (predicted vs actual + hit/miss) and exports it as CSV."""

    async def list_prediction_logs(
        self,
        db: AsyncSession,
        log_filter: AdminPredictionLogFilterDTO,
        params: Params,
    ) -> AbstractPage:
        query = select(AiPredictionLogs)
        query = log_filter.filter(query)
        query = log_filter.sort(query)
        return await apaginate(
            db,
            query,
            params,
            transformer=lambda rows: [self._serialize(row) for row in rows],
        )

    async def export_csv(
        self, db: AsyncSession, log_filter: AdminPredictionLogFilterDTO
    ) -> str:
        query = select(AiPredictionLogs)
        query = log_filter.filter(query)
        query = log_filter.sort(query)
        query = query.limit(PREDICTION_EXPORT_MAX_ROWS)
        rows = (await db.execute(query)).scalars().all()

        buffer = io.StringIO()
        writer = csv.writer(buffer)
        writer.writerow(_EXPORT_HEADER)
        for row in rows:
            writer.writerow(
                [
                    row.created_at.isoformat(),
                    row.advisor,
                    row.input_summary,
                    row.predicted_label,
                    (
                        row.predicted_confidence
                        if row.predicted_confidence is not None
                        else ""
                    ),
                    row.actual_label or "",
                    row.outcome,
                ]
            )
        return buffer.getvalue()

    @staticmethod
    def _serialize(row: AiPredictionLogs) -> PredictionLogItemDTO:
        return PredictionLogItemDTO(
            prediction_log_id=str(row.id),
            created_at=row.created_at,
            advisor=row.advisor,
            input_summary=row.input_summary,
            predicted_label=row.predicted_label,
            predicted_confidence=row.predicted_confidence,
            actual_label=row.actual_label,
            outcome=row.outcome,
            subject_ref=row.subject_ref,
        )
