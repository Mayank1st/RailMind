import json
import logging
from datetime import date

from redis.asyncio import Redis

from app.core.constants.live_status import (
    CACHE_TTL_LIVE_STATUS,
    CACHE_TTL_LIVE_STATUS_STALE,
    LIVE_STATUS_FRESH_PREFIX,
    LIVE_STATUS_PROVIDER_NAME,
    LIVE_STATUS_QUOTA_PREFIX,
    LIVE_STATUS_STALE_PREFIX,
)
from app.core.exceptions import (
    LiveStatusUnavailableError,
    LiveTrainNotFoundError,
    LiveTrainNotRunningError,
)
from app.integrations.live_status.exceptions import (
    ProviderError,
    ProviderInvalidTrainError,
    ProviderQuotaExceededError,
    ProviderTrainNotRunningError,
)
from app.integrations.live_status.train_running_api import TrainRunningApiProvider
from app.schemas.Response.liveStatusResponseDTO import (
    LiveStatusResponseDTO,
    StationProgressDTO,
)

logger = logging.getLogger(__name__)


class LiveStatusService:
    def __init__(self) -> None:
        self.provider = TrainRunningApiProvider()

    async def get_live_status(
        self,
        train_number: str,
        journey_date: date,
        redis: Redis,
    ) -> LiveStatusResponseDTO:
        fresh_key = f"{LIVE_STATUS_FRESH_PREFIX}{train_number}:{journey_date}"
        stale_key = f"{LIVE_STATUS_STALE_PREFIX}{train_number}:{journey_date}"

        # 1. Fresh cache
        fresh = await redis.get(fresh_key)
        if fresh:
            logger.info("live status cache HIT: %s %s", train_number, journey_date)
            return self._to_dto(json.loads(fresh), is_stale=False)

        # 2. Cache miss → call provider (track daily quota usage)
        await self._bump_quota(redis)
        try:
            result = await self.provider.fetch_live_status(train_number, journey_date)
        except ProviderInvalidTrainError as e:
            logger.warning("train not found: %s — %s", train_number, e)
            raise LiveTrainNotFoundError()
        except ProviderTrainNotRunningError as e:
            logger.warning(
                "train not running: %s %s — %s", train_number, journey_date, e
            )
            raise LiveTrainNotRunningError()
        except (ProviderQuotaExceededError, ProviderError) as e:
            logger.error("provider failed for %s: %s", train_number, e)
            # 3. Stale fallback
            stale = await redis.get(stale_key)
            if stale:
                logger.info("returning STALE for %s", train_number)
                return self._to_dto(json.loads(stale), is_stale=True)
            raise LiveStatusUnavailableError()

        # 4. Cache fresh + stale
        payload = result.model_dump_json()
        await redis.setex(fresh_key, CACHE_TTL_LIVE_STATUS, payload)
        await redis.setex(stale_key, CACHE_TTL_LIVE_STATUS_STALE, payload)

        return self._to_dto(json.loads(payload), is_stale=False)

    @staticmethod
    async def _bump_quota(redis: Redis) -> None:
        key = f"{LIVE_STATUS_QUOTA_PREFIX}{date.today().isoformat()}"
        count = await redis.incr(key)
        if count == 1:
            await redis.expire(key, CACHE_TTL_LIVE_STATUS_STALE)

    @staticmethod
    def _to_dto(raw: dict, is_stale: bool) -> LiveStatusResponseDTO:
        return LiveStatusResponseDTO(
            train_number=raw["train_number"],
            train_name=raw["train_name"],
            journey_date=raw["journey_date"],
            current_station_code=raw.get("current_station_code"),
            current_station_name=raw.get("current_station_name"),
            current_delay_minutes=raw.get("current_delay_minutes", 0),
            last_reported_at=raw.get("last_reported_at"),
            expected_platform=raw.get("expected_platform"),
            route=[StationProgressDTO(**s) for s in raw.get("route", [])],
            is_stale=is_stale,
            source=LIVE_STATUS_PROVIDER_NAME,
            fetched_at=raw["fetched_at"],
        )


live_status_service = LiveStatusService()
