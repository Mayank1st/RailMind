from fastapi import APIRouter

from app.domain.admin.admin_router.admin_auth import router as admin_auth_router
from app.domain.admin.admin_router.admin_ops import router as admin_ops_router
from app.domain.admin.admin_router.admin_ai_control import (
    router as admin_ai_control_router,
)
from app.domain.admin.admin_router.admin_config import router as admin_config_router
from app.domain.admin.admin_router.admin_entities import router as admin_entities_router
from app.domain.admin.admin_router.admin_master_data import (
    router as admin_master_data_router,
)
from app.domain.admin.admin_router.admin_dashboard import (
    router as admin_dashboard_router,
)

router = APIRouter(prefix="/admin")

router.include_router(admin_auth_router)
router.include_router(admin_ops_router)
router.include_router(admin_ai_control_router)
router.include_router(admin_config_router)
router.include_router(admin_entities_router)
router.include_router(admin_master_data_router)
router.include_router(admin_dashboard_router)
