from fastapi import APIRouter, Depends
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db, get_redis, rate_limit
from app.core.response import ok
from app.schemas.Request.fareRequestDTO import FareEnquiryRequestDTO
from app.services.fare_service import fare_enquiry_service

router = APIRouter(prefix="/fare", tags=["Fare"])


@router.get(
    "/enquiry",
    dependencies=[Depends(rate_limit(limit=30, scope="fare_enquiry"))],
)
async def fare_enquiry(
    payload: FareEnquiryRequestDTO = Depends(),
    db: AsyncSession = Depends(get_db),
    redis: Redis = Depends(get_redis),
):
    data, cached = await fare_enquiry_service.get_fare_enquiry(payload, db, redis)
    return ok(
        data=data,
        message="Fare calculated successfully",
        meta={"cached": cached},
    )
