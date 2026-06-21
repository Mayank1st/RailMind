from fastapi import APIRouter

from app.domain.health.health_service.health_service import HealthCheckService

router = APIRouter(prefix="/health-check", tags=["Health Check"])


@router.get("/health-check-status")
async def health_check():
    return await HealthCheckService.get_health_check_status()
