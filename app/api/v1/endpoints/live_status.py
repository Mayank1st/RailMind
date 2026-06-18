from datetime import date

from fastapi import APIRouter, Depends, Query
from redis.asyncio import Redis

from app.api.deps import get_redis, rate_limit
from app.core.constants.live_status import RATE_LIMIT_LIVE_STATUS_PER_MINUTE
from app.core.response import ok
from app.services.live_status_service import live_status_service

router = APIRouter(prefix="/train", tags=["Live Status"])


@router.get(
    "/{train_number}/live-status",
    dependencies=[
        Depends(
            rate_limit(limit=RATE_LIMIT_LIVE_STATUS_PER_MINUTE, scope="live_status")
        )
    ],
)
async def get_live_status(
    train_number: str,
    journey_date: date = Query(..., description="Journey departure date (YYYY-MM-DD)"),
    redis: Redis = Depends(get_redis),
):
    data = await live_status_service.get_live_status(train_number, journey_date, redis)
    return ok(
        data=data.model_dump(mode="json"),
        message="Live status fetched",
        meta={"source": data.source, "is_stale": data.is_stale},
    )
