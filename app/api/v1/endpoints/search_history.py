from fastapi import APIRouter, Depends, Query
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_db, get_redis
from app.core.constants.search_history import (
    RECENT_SEARCH_DEFAULT_LIMIT,
    RECENT_SEARCH_LIMIT_CAP,
)
from app.core.response import ok
from app.services.search_history_service import search_history_service

router = APIRouter(prefix="/search-history", tags=["Search History"])


# Authenticated-only. Guests keep recent searches in FE localStorage; logging is
# implicit (fired from /train/search), so there is no public POST here.
@router.get("/recent")
async def get_recent_searches(
    limit: int = Query(
        default=RECENT_SEARCH_DEFAULT_LIMIT, ge=1, le=RECENT_SEARCH_LIMIT_CAP
    ),
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    redis: Redis = Depends(get_redis),
):
    data = await search_history_service.get_recent_searches(
        db=db, redis=redis, user_id=current_user["sub"], limit=limit
    )
    return ok(data=data, message="Recent searches fetched", meta={"count": len(data)})
