import uuid

from fastapi import APIRouter, Depends, Request, Response
from fastapi_filter import FilterDepends
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db, get_redis
from app.core.pagination import Params, paginated
from app.core.permissions import IsAdmin, IsAgent
from app.core.response import ok
from app.domain.admin.admin_service.admin_ai_control_service import (
    AdminAiControlService,
)
from app.domain.admin.admin_service.admin_llm_usage_service import (
    AdminLlmUsageService,
)
from app.domain.admin.admin_service.admin_model_versions_service import (
    AdminModelVersionsService,
)
from app.domain.admin.admin_service.admin_prediction_logs_service import (
    AdminPredictionLogsService,
)
from app.domain.admin.admin_service.admin_retrain_service import AdminRetrainService
from app.domain.admin.dto.admin_ai_control_request_dto import (
    SetAdvisorStateRequestDTO,
)
from app.domain.admin.dto.admin_model_versions_request_dto import (
    ActivateModelVersionRequestDTO,
)
from app.domain.admin.dto.admin_prediction_logs_filter_dto import (
    AdminPredictionLogFilterDTO,
)
from app.domain.admin.dto.admin_retrain_request_dto import (
    PromoteCandidateRequestDTO,
    TriggerRetrainRequestDTO,
)

router = APIRouter(prefix="/ai", tags=["Admin AI Control"])

admin_ai_control_service = AdminAiControlService()
admin_model_versions_service = AdminModelVersionsService()
admin_retrain_service = AdminRetrainService()
admin_prediction_logs_service = AdminPredictionLogsService()
admin_llm_usage_service = AdminLlmUsageService()


def _client_ip(request: Request) -> str | None:
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else None


# ── Advisor toggles ──────────────────────────────────────────────────────────


@router.get("/advisors")
async def list_admin_advisors(
    current_user: dict = IsAgent,
    db: AsyncSession = Depends(get_db),
    redis: Redis = Depends(get_redis),
):
    data = await admin_ai_control_service.list_advisors(db, redis)
    return ok(data=data, message="Advisor toggles fetched successfully.")


@router.patch("/advisors/{advisor_key}")
async def set_admin_advisor_state(
    advisor_key: str,
    payload: SetAdvisorStateRequestDTO,
    request: Request,
    current_user: dict = IsAdmin,
    db: AsyncSession = Depends(get_db),
    redis: Redis = Depends(get_redis),
):
    data = await admin_ai_control_service.set_advisor_state(
        advisor_key, payload.state.value, current_user, _client_ip(request), db, redis
    )
    return ok(data=data, message="Advisor toggle updated successfully.")


# ── Model versions ───────────────────────────────────────────────────────────


@router.get("/models")
async def list_admin_model_versions(
    current_user: dict = IsAgent,
    db: AsyncSession = Depends(get_db),
    redis: Redis = Depends(get_redis),
):
    data = await admin_model_versions_service.list_active(db, redis)
    return ok(data=data, message="Model versions fetched successfully.")


@router.get("/models/{advisor_key}")
async def get_admin_model_versions(
    advisor_key: str,
    current_user: dict = IsAgent,
    db: AsyncSession = Depends(get_db),
    redis: Redis = Depends(get_redis),
):
    data = await admin_model_versions_service.get_versions(db, redis, advisor_key)
    return ok(data=data, message="Model version history fetched successfully.")


@router.post("/models/{advisor_key}/activate")
async def activate_admin_model_version(
    advisor_key: str,
    payload: ActivateModelVersionRequestDTO,
    request: Request,
    current_user: dict = IsAdmin,
    db: AsyncSession = Depends(get_db),
    redis: Redis = Depends(get_redis),
):
    data = await admin_model_versions_service.activate_version(
        advisor_key, payload.version_label, current_user, _client_ip(request), db, redis
    )
    return ok(data=data, message="Model version activated.")


@router.post("/models/{advisor_key}/fallback")
async def force_admin_model_fallback(
    advisor_key: str,
    request: Request,
    current_user: dict = IsAdmin,
    db: AsyncSession = Depends(get_db),
    redis: Redis = Depends(get_redis),
):
    data = await admin_model_versions_service.force_fallback(
        advisor_key, current_user, _client_ip(request), db, redis
    )
    return ok(data=data, message="Advisor switched to rule-based fallback.")


# ── Retrain ──────────────────────────────────────────────────────────────────


@router.post("/retrain")
async def trigger_admin_retrain(
    payload: TriggerRetrainRequestDTO,
    request: Request,
    current_user: dict = IsAdmin,
    db: AsyncSession = Depends(get_db),
):
    data = await admin_retrain_service.trigger_retrain(
        payload, current_user, _client_ip(request), db
    )
    return ok(data=data, message="Retraining job queued.")


@router.get("/retrain")
async def list_admin_retrain_candidates(
    current_user: dict = IsAgent,
    db: AsyncSession = Depends(get_db),
):
    data = await admin_retrain_service.list_candidates(db)
    return ok(data=data, message="Retrain candidates fetched successfully.")


@router.get("/retrain/{candidate_id}")
async def get_admin_retrain_report(
    candidate_id: uuid.UUID,
    current_user: dict = IsAgent,
    db: AsyncSession = Depends(get_db),
):
    data = await admin_retrain_service.get_report(db, candidate_id)
    return ok(data=data, message="Retrain report fetched successfully.")


@router.post("/retrain/{candidate_id}/promote")
async def promote_admin_retrain_candidate(
    candidate_id: uuid.UUID,
    payload: PromoteCandidateRequestDTO,
    request: Request,
    current_user: dict = IsAdmin,
    db: AsyncSession = Depends(get_db),
    redis: Redis = Depends(get_redis),
):
    data = await admin_retrain_service.promote(
        candidate_id, payload.reason, current_user, _client_ip(request), db, redis
    )
    return ok(data=data, message="Candidate promoted to active.")


# ── Prediction logs ──────────────────────────────────────────────────────────


@router.get("/predictions")
async def list_admin_prediction_logs(
    log_filter: AdminPredictionLogFilterDTO = FilterDepends(
        AdminPredictionLogFilterDTO
    ),
    params: Params = Depends(),
    current_user: dict = IsAgent,
    db: AsyncSession = Depends(get_db),
):
    page = await admin_prediction_logs_service.list_prediction_logs(
        db, log_filter, params
    )
    return paginated(page, message="Prediction logs fetched successfully.")


@router.get("/predictions/export")
async def export_admin_prediction_logs(
    log_filter: AdminPredictionLogFilterDTO = FilterDepends(
        AdminPredictionLogFilterDTO
    ),
    current_user: dict = IsAgent,
    db: AsyncSession = Depends(get_db),
):
    csv_text = await admin_prediction_logs_service.export_csv(db, log_filter)
    return Response(
        content=csv_text,
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=prediction_logs.csv"},
    )


# ── LLM usage ────────────────────────────────────────────────────────────────


@router.get("/llm-usage")
async def get_admin_llm_usage(
    hours: int = 24,
    current_user: dict = IsAgent,
    db: AsyncSession = Depends(get_db),
):
    data = await admin_llm_usage_service.hourly_usage(db, hours)
    return ok(data=data, message="LLM usage fetched successfully.")


@router.get("/llm-usage/export")
async def export_admin_llm_usage(
    hours: int = 24,
    current_user: dict = IsAgent,
    db: AsyncSession = Depends(get_db),
):
    csv_text = await admin_llm_usage_service.export_csv(db, hours)
    return Response(
        content=csv_text,
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=llm_usage.csv"},
    )
