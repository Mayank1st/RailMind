from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.common_service import CommonService
from app.api.deps import get_db
from app.core.response import ok

router = APIRouter(prefix="/common", tags=["Common"])

common_service = CommonService()


@router.get("/stations")
async def get_all_stations(db: AsyncSession = Depends(get_db)):
    data = await common_service.get_all_stations(db)
    return ok(data=data, message="All Stations Fetched Successfully.")
