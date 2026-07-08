import uuid

from fastapi import APIRouter, Depends, Query, Request
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db, get_redis
from app.core.permissions import IsAdmin, IsAgent
from app.core.response import ok
from app.domain.admin.admin_service.admin_fare_service import AdminFareService
from app.domain.admin.admin_service.admin_holidays_service import AdminHolidaysService
from app.domain.admin.admin_service.admin_quota_service import AdminQuotaService
from app.domain.admin.admin_service.admin_rate_limits_service import (
    AdminRateLimitsService,
)
from app.domain.admin.dto.admin_fare_request_dto import (
    EditFareRuleRequestDTO,
    FarePreviewRequestDTO,
    NewFareVersionRequestDTO,
    QuickEditFareRuleRequestDTO,
)
from app.domain.admin.dto.admin_holidays_request_dto import (
    CreateHolidayRequestDTO,
    UpdateHolidayRequestDTO,
)
from app.domain.admin.dto.admin_quota_request_dto import (
    CreateQuotaRequestDTO,
    UpdateQuotaRequestDTO,
)
from app.domain.admin.dto.admin_rate_limits_request_dto import (
    CreateRateLimitRequestDTO,
    UpdateRateLimitRequestDTO,
)

router = APIRouter(tags=["Admin Config"])

admin_fare_service = AdminFareService()
admin_holidays_service = AdminHolidaysService()
admin_rate_limits_service = AdminRateLimitsService()
admin_quota_service = AdminQuotaService()


def _client_ip(request: Request) -> str | None:
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else None


# ── Fare rules ───────────────────────────────────────────────────────────────


@router.get("/config/fare-rules")
async def get_admin_fare_rules(
    current_user: dict = IsAgent,
    db: AsyncSession = Depends(get_db),
):
    data = await admin_fare_service.get_current_rules(db)
    return ok(data=data, message="Fare rules fetched successfully.")


@router.post("/config/fare-rules/preview")
async def preview_admin_fare(
    payload: FarePreviewRequestDTO,
    current_user: dict = IsAgent,
):
    data = admin_fare_service.preview_fare(payload)
    return ok(data=data, message="Fare preview computed.")


@router.get("/config/fare-rules/versions")
async def list_admin_fare_versions(
    current_user: dict = IsAgent,
    db: AsyncSession = Depends(get_db),
):
    data = await admin_fare_service.list_versions(db)
    return ok(data=data, message="Fare versions fetched successfully.")


@router.post("/config/fare-rules/versions")
async def create_admin_fare_version(
    payload: NewFareVersionRequestDTO,
    request: Request,
    current_user: dict = IsAdmin,
    db: AsyncSession = Depends(get_db),
):
    data = await admin_fare_service.create_version(
        payload, current_user, _client_ip(request), db
    )
    return ok(data=data, message="Draft fare version created.")


@router.get("/config/fare-rules/versions/{version_id}")
async def get_admin_fare_version(
    version_id: uuid.UUID,
    current_user: dict = IsAgent,
    db: AsyncSession = Depends(get_db),
):
    data = await admin_fare_service.get_version(version_id, db)
    return ok(data=data, message="Fare version fetched successfully.")


@router.patch("/config/fare-rules/versions/{version_id}/rules/{train_class}")
async def edit_admin_fare_rule(
    version_id: uuid.UUID,
    train_class: str,
    payload: EditFareRuleRequestDTO,
    request: Request,
    current_user: dict = IsAdmin,
    db: AsyncSession = Depends(get_db),
):
    data = await admin_fare_service.edit_rule(
        version_id, train_class, payload, current_user, _client_ip(request), db
    )
    return ok(data=data, message="Fare rule updated.")


@router.post("/config/fare-rules/versions/{version_id}/publish")
async def publish_admin_fare_version(
    version_id: uuid.UUID,
    request: Request,
    current_user: dict = IsAdmin,
    db: AsyncSession = Depends(get_db),
):
    data = await admin_fare_service.publish_version(
        version_id, current_user, _client_ip(request), db
    )
    return ok(data=data, message="Fare version published.")


@router.patch("/config/fare-rules/rules/{train_class}")
async def quick_edit_admin_fare_rule(
    train_class: str,
    payload: QuickEditFareRuleRequestDTO,
    request: Request,
    current_user: dict = IsAdmin,
    db: AsyncSession = Depends(get_db),
):
    data = await admin_fare_service.quick_edit_live(
        train_class, payload, current_user, _client_ip(request), db
    )
    return ok(data=data, message="Fare rule saved as a new live version.")


# ── Holiday calendar ─────────────────────────────────────────────────────────


@router.get("/config/holidays")
async def list_admin_holidays(
    region: str | None = Query(None),
    demand_tier: str | None = Query(
        None, description="LOW | MEDIUM | HIGH | VERY_HIGH"
    ),
    status: str | None = Query(None, description="active | disabled"),
    current_user: dict = IsAgent,
    db: AsyncSession = Depends(get_db),
):
    data = await admin_holidays_service.list_holidays(db, region, demand_tier, status)
    return ok(data=data, message="Holiday calendar fetched successfully.")


@router.post("/config/holidays")
async def create_admin_holiday(
    payload: CreateHolidayRequestDTO,
    request: Request,
    current_user: dict = IsAdmin,
    db: AsyncSession = Depends(get_db),
):
    data = await admin_holidays_service.create_holiday(
        payload, current_user, _client_ip(request), db
    )
    return ok(data=data, message="Holiday added successfully.")


@router.patch("/config/holidays/{holiday_id}")
async def update_admin_holiday(
    holiday_id: uuid.UUID,
    payload: UpdateHolidayRequestDTO,
    request: Request,
    current_user: dict = IsAdmin,
    db: AsyncSession = Depends(get_db),
):
    data = await admin_holidays_service.update_holiday(
        holiday_id, payload, current_user, _client_ip(request), db
    )
    return ok(data=data, message="Holiday updated successfully.")


@router.delete("/config/holidays/{holiday_id}")
async def delete_admin_holiday(
    holiday_id: uuid.UUID,
    request: Request,
    current_user: dict = IsAdmin,
    db: AsyncSession = Depends(get_db),
):
    data = await admin_holidays_service.delete_holiday(
        holiday_id, current_user, _client_ip(request), db
    )
    return ok(data=data, message="Holiday removed successfully.")


# ── Rate limits ──────────────────────────────────────────────────────────────


@router.get("/config/rate-limits")
async def list_admin_rate_limits(
    current_user: dict = IsAgent,
    db: AsyncSession = Depends(get_db),
    redis: Redis = Depends(get_redis),
):
    data = await admin_rate_limits_service.list_rate_limits(db, redis)
    return ok(data=data, message="Rate limits fetched successfully.")


@router.post("/config/rate-limits")
async def create_admin_rate_limit(
    payload: CreateRateLimitRequestDTO,
    request: Request,
    current_user: dict = IsAdmin,
    db: AsyncSession = Depends(get_db),
    redis: Redis = Depends(get_redis),
):
    data = await admin_rate_limits_service.create_rate_limit(
        payload, current_user, _client_ip(request), db, redis
    )
    return ok(data=data, message="Rate limit added successfully.")


@router.patch("/config/rate-limits/{rate_limit_id}")
async def update_admin_rate_limit(
    rate_limit_id: uuid.UUID,
    payload: UpdateRateLimitRequestDTO,
    request: Request,
    current_user: dict = IsAdmin,
    db: AsyncSession = Depends(get_db),
    redis: Redis = Depends(get_redis),
):
    data = await admin_rate_limits_service.update_rate_limit(
        rate_limit_id, payload, current_user, _client_ip(request), db, redis
    )
    return ok(data=data, message="Rate limit updated successfully.")


@router.delete("/config/rate-limits/{rate_limit_id}")
async def delete_admin_rate_limit(
    rate_limit_id: uuid.UUID,
    request: Request,
    current_user: dict = IsAdmin,
    db: AsyncSession = Depends(get_db),
    redis: Redis = Depends(get_redis),
):
    data = await admin_rate_limits_service.delete_rate_limit(
        rate_limit_id, current_user, _client_ip(request), db, redis
    )
    return ok(data=data, message="Rate limit removed successfully.")


# ── Quota allocation ─────────────────────────────────────────────────────────


@router.get("/config/quota-allocations")
async def list_admin_quota_allocations(
    current_user: dict = IsAgent,
    db: AsyncSession = Depends(get_db),
):
    data = await admin_quota_service.list_quota_allocations(db)
    return ok(data=data, message="Quota allocations fetched successfully.")


@router.post("/config/quota-allocations")
async def create_admin_quota_allocation(
    payload: CreateQuotaRequestDTO,
    request: Request,
    current_user: dict = IsAdmin,
    db: AsyncSession = Depends(get_db),
):
    data = await admin_quota_service.create_quota_allocation(
        payload, current_user, _client_ip(request), db
    )
    return ok(data=data, message="Quota allocation added successfully.")


@router.patch("/config/quota-allocations/{quota_id}")
async def update_admin_quota_allocation(
    quota_id: uuid.UUID,
    payload: UpdateQuotaRequestDTO,
    request: Request,
    current_user: dict = IsAdmin,
    db: AsyncSession = Depends(get_db),
):
    data = await admin_quota_service.update_quota_allocation(
        quota_id, payload, current_user, _client_ip(request), db
    )
    return ok(data=data, message="Quota allocation updated successfully.")


@router.delete("/config/quota-allocations/{quota_id}")
async def delete_admin_quota_allocation(
    quota_id: uuid.UUID,
    request: Request,
    current_user: dict = IsAdmin,
    db: AsyncSession = Depends(get_db),
):
    data = await admin_quota_service.delete_quota_allocation(
        quota_id, current_user, _client_ip(request), db
    )
    return ok(data=data, message="Quota allocation removed successfully.")
