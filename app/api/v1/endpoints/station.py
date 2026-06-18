from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db
from app.core.response import ok
from app.services.station_cluster_service import station_cluster_service

router = APIRouter(prefix="/stations", tags=["Stations"])


@router.get("/{station_code}/cluster")
async def get_station_cluster(
    station_code: str,
    db: AsyncSession = Depends(get_db),
):
    data = await station_cluster_service.get_cluster_view(db, station_code)
    return ok(data=data, message="Station cluster fetched")
