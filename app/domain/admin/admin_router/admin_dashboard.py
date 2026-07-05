from fastapi import APIRouter, Depends, Query
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db, get_redis
from app.core.permissions import IsAgent
from app.core.response import ok
from app.domain.admin.admin_service.admin_dashboard_service import AdminDashboardService
from app.domain.admin.constants.admin_dashboard import MetricsRange

router = APIRouter(prefix="/metrics", tags=["Admin Dashboard"])

admin_dashboard_service = AdminDashboardService()


@router.get("/overview")
async def get_overview_metrics(
    time_range: MetricsRange = Query(MetricsRange.LAST_7D, alias="range"),
    current_user: dict = IsAgent,
    db: AsyncSession = Depends(get_db),
    redis: Redis = Depends(get_redis),
):
    data = await admin_dashboard_service.get_overview(time_range.value, db, redis)
    return ok(data=data, message="Overview metrics fetched successfully.")
