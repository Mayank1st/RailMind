from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db
from app.core.response import ok
from app.domain.trending.trending_service.trending_service import trending_service

router = APIRouter(prefix="/trending", tags=["Trending"])


@router.get("/weekly-routes")
async def get_weekly_trending_routes(db: AsyncSession = Depends(get_db)):
    data = await trending_service.get_latest_trending(db)
    return ok(
        data=data,
        message="Weekly trending routes fetched",
        meta={"count": len(data["routes"])},
    )


@router.get("/popular-destinations")
async def get_popular_destinations(db: AsyncSession = Depends(get_db)):
    data = await trending_service.get_latest_popular_destinations(db)
    return ok(
        data=data,
        message="Popular destinations fetched",
        meta={"count": len(data["destinations"])},
    )
