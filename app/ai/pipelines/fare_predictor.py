import json
import logging
from datetime import date

from fastapi import APIRouter, Depends
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_db, get_redis, rate_limit
from app.config import settings
from app.core.response import ok
from app.domain.auth.constants.auth_user import CACHE_TTL_SEAT_AVAILABILITY
from app.domain.fare.constants.fare_advisor import (
    AdvisorDecision,
    AdvisorSource,
    BookingVelocity,
    CONFIDENCE_LOW,
    ERROR_CODE_ADVISOR,
)
from app.domain.fare.dto.fare_advisor_dto import (
    FareAdvisorBatchItemDTO,
    FareAdvisorResponseDTO,
)
from app.domain.fare.fare_service.fare_advisor_model_service import (
    FareAdvisorModelService,
)
from app.domain.fare.fare_service.fare_advisor_reason_service import (
    FareAdvisorReasonService,
)
from app.domain.fare.fare_service.fare_advisor_rules_service import (
    FareAdvisorRulesService,
)

logger = logging.getLogger(__name__)

# Decision is availability-driven (high churn) -> short TTL. Cached WITHOUT the
# Gemini reason or `explain`, so the badge (list) and the full nudge (expand)
# share one decision; only the reason is layered on top at serve time.
ADVISOR_CACHE_TTL = CACHE_TTL_SEAT_AVAILABILITY

router = APIRouter(prefix="/fare")

fare_advisor_rules_service = FareAdvisorRulesService()
fare_advisor_model_service = FareAdvisorModelService()
fare_advisor_reason_service = FareAdvisorReasonService()


def _service():
    """Route to L2 when the model artifact is present, else L1 rules."""
    if fare_advisor_model_service.is_available():
        return fare_advisor_model_service
    return fare_advisor_rules_service


def _cache_key(
    train_number: str, train_class: str, quota: str, journey_date: date
) -> str:
    return f"fareadv:{train_number}:{train_class}:{quota}:{journey_date}"


async def _cache_get(redis: Redis, key: str) -> dict | None:
    try:
        raw = await redis.get(key)
        return json.loads(raw) if raw else None
    except Exception:
        return None  # cache is best-effort — never block the advisor


async def _cache_set(redis: Redis, key: str, data: dict) -> None:
    try:
        await redis.setex(key, ADVISOR_CACHE_TTL, json.dumps(data))
    except Exception:
        pass


@router.get(
    "/advisor",
    dependencies=[Depends(rate_limit(limit=60, scope="fare_advisor"))],
)
async def get_fare_advisor(
    train_number: str,
    source_station_code: str,
    destination_station_code: str,
    train_class: str,
    journey_date: date,
    quota: str = "GN",
    explain: bool = True,  # L3 Gemini nudge; set false to skip the LLM call
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    redis: Redis = Depends(get_redis),
):
    key = _cache_key(train_number, train_class, quota, journey_date)
    cached = False
    data = await _cache_get(redis, key)
    if data is not None:
        cached = True
    else:
        try:
            data = await _service().advise(
                db=db,
                train_number=train_number,
                train_class=train_class,
                quota=quota,
                journey_date=journey_date,
            )
            await _cache_set(redis, key, data)
        except Exception:
            # Advisor must never block the booking flow — degrade to a safe default.
            logger.exception("%s fare advisor failed", ERROR_CODE_ADVISOR)
            await db.rollback()
            data = _safe_default(journey_date)

    # L3 — layer the Gemini nudge on top of the (cached or fresh) decision.
    if explain:
        data["reason"] = await fare_advisor_reason_service.generate_reason(data)

    return ok(
        data=FareAdvisorResponseDTO.model_validate(data),
        message="Fare advice generated successfully.",
        meta={
            "confidence_threshold": settings.AI_CONFIDENCE_THRESHOLD,
            "cached": cached,
        },
    )


@router.post(
    "/advisor/batch",
    dependencies=[Depends(rate_limit(limit=30, scope="fare_advisor_batch"))],
)
async def get_fare_advisor_batch(
    items: list[FareAdvisorBatchItemDTO],
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    redis: Redis = Depends(get_redis),
):
    # Badge-only (no Gemini): one call for a whole search list. Cache-first per
    # journey; compute only the misses in a single batched DB + model pass.
    results: list[dict | None] = [None] * len(items)
    to_compute: list[FareAdvisorBatchItemDTO] = []
    miss_idx: list[int] = []
    for i, item in enumerate(items):
        data = await _cache_get(
            redis,
            _cache_key(
                item.train_number, item.train_class, item.quota, item.journey_date
            ),
        )
        if data is not None:
            results[i] = data
        else:
            to_compute.append(item)
            miss_idx.append(i)

    if to_compute:
        cacheable = True
        try:
            computed = await _service().advise_batch(
                db, [item.model_dump() for item in to_compute]
            )
        except Exception:
            logger.exception("%s fare advisor batch failed", ERROR_CODE_ADVISOR)
            await db.rollback()
            computed = [_safe_default(item.journey_date) for item in to_compute]
            cacheable = False  # don't cache error fallbacks
        for k, i in enumerate(miss_idx):
            results[i] = computed[k]
            if cacheable:
                item = items[i]
                await _cache_set(
                    redis,
                    _cache_key(
                        item.train_number,
                        item.train_class,
                        item.quota,
                        item.journey_date,
                    ),
                    computed[k],
                )

    return ok(
        data=[FareAdvisorResponseDTO.model_validate(r) for r in results],
        message="Fare advice generated successfully.",
        meta={
            "confidence_threshold": settings.AI_CONFIDENCE_THRESHOLD,
            "count": len(results),
        },
    )


def _safe_default(journey_date: date) -> dict:
    """Last-resort response when the advisor errors — honest low-confidence
    BOOK_NOW so we never silently tell a user to wait on no data."""
    days_to_journey = (journey_date - date.today()).days
    return {
        "decision": AdvisorDecision.BOOK_NOW.value,
        "confidence": CONFIDENCE_LOW,
        "reason": "We couldn't read live availability — booking early is the safer choice.",
        "signals": {
            "fill_rate": None,
            "days_to_journey": days_to_journey,
            "booking_velocity": BookingVelocity.LOW.value,
            "waitlist_pressure": None,
        },
        "source": AdvisorSource.RULES.value,
    }
