import json
import uuid
from typing import Optional

from redis.asyncio import Redis
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import RATE_LIMIT_CONFIG_PREFIX, rate_limit_counter_key
from app.core.exceptions import RailMindException
from app.db.models.rate_limit_config import RateLimitConfigs
from app.domain.admin.admin_service.admin_audit_service import AdminAuditService
from app.domain.admin.constants.admin_audit import AuditAction, AuditTargetType
from app.domain.admin.constants.admin_rate_limits import (
    ERR_RATE_LIMIT_DUPLICATE,
    ERR_RATE_LIMIT_NOT_FOUND,
    NEAR_RATIO,
    SCOPE_LABELS,
    STATUS_AT_CAP,
    STATUS_NEAR,
    STATUS_OK,
    RateLimitScope,
)
from app.domain.admin.dto.admin_rate_limits_request_dto import (
    CreateRateLimitRequestDTO,
    UpdateRateLimitRequestDTO,
)
from app.domain.admin.dto.admin_rate_limits_response_dto import RateLimitItemDTO
from app.utils.logger import logger

_AUDIT_SNAPSHOT_FIELDS = ("endpoint", "scope_type", "window_seconds", "request_limit")

# Bound the CURRENT-PEAK scan so a huge keyspace can't stall the admin list.
_PEAK_SCAN_MAX_BATCHES = 20
_PEAK_SCAN_COUNT = 200

audit_service = AdminAuditService()


class AdminRateLimitsService:
    """Config → Rate Limits CRUD (per-endpoint request ceilings), audited.

    The source of truth is the rate_limit_configs table; every write also mirrors
    the row into Redis (RATE_LIMIT_CONFIG_PREFIX + endpoint) so the hot-path
    `rate_limit` dependency can apply it with a single fast GET. CURRENT PEAK /
    STATUS are read live from the Redis fixed-window counters.
    """

    # ── Read ────────────────────────────────────────────────────────────────

    async def list_rate_limits(
        self, db: AsyncSession, redis: Redis
    ) -> list[RateLimitItemDTO]:
        rows = (
            (
                await db.execute(
                    select(RateLimitConfigs).order_by(RateLimitConfigs.endpoint)
                )
            )
            .scalars()
            .all()
        )

        items: list[RateLimitItemDTO] = []
        for row in rows:
            # side-effect: keep the hot-path cache warm (survives a Redis flush
            # once an admin views this screen).
            await self._write_cache(redis, row)
            peak = await self._current_peak(redis, row.endpoint, row.scope_type)
            items.append(self._serialize(row, peak))
        return items

    # ── Actions (audited, super-admin) ──────────────────────────────────────

    async def create_rate_limit(
        self,
        payload: CreateRateLimitRequestDTO,
        current_user: dict,
        ip: Optional[str],
        db: AsyncSession,
        redis: Redis,
    ) -> RateLimitItemDTO:
        await self._ensure_endpoint_free(db, payload.endpoint, exclude_id=None)
        row = RateLimitConfigs(
            endpoint=payload.endpoint,
            scope_type=payload.scope_type.value,
            window_seconds=payload.window_seconds,
            request_limit=payload.limit,
            created_by=self._actor_uuid(current_user),
        )
        db.add(row)
        await db.flush()
        await self._audit(
            db,
            current_user,
            AuditAction.RATE_LIMIT_CREATED.value,
            row.id,
            before=None,
            after=self._snapshot(row),
            ip=ip,
        )
        await db.flush()
        await self._write_cache(redis, row)
        logger.info("Rate limit created id=%s endpoint=%s", row.id, row.endpoint)
        peak = await self._current_peak(redis, row.endpoint, row.scope_type)
        return self._serialize(row, peak)

    async def update_rate_limit(
        self,
        rate_limit_id: uuid.UUID,
        payload: UpdateRateLimitRequestDTO,
        current_user: dict,
        ip: Optional[str],
        db: AsyncSession,
        redis: Redis,
    ) -> RateLimitItemDTO:
        row = await self._load(rate_limit_id, db)
        changes = payload.model_dump(exclude_none=True)
        if not changes:
            peak = await self._current_peak(redis, row.endpoint, row.scope_type)
            return self._serialize(row, peak)

        old_endpoint = row.endpoint
        if "endpoint" in changes and changes["endpoint"] != old_endpoint:
            await self._ensure_endpoint_free(db, changes["endpoint"], exclude_id=row.id)

        before = self._snapshot(row)
        for field, value in changes.items():
            column = "request_limit" if field == "limit" else field
            setattr(row, column, value.value if hasattr(value, "value") else value)
        await db.flush()
        await self._audit(
            db,
            current_user,
            AuditAction.RATE_LIMIT_UPDATED.value,
            row.id,
            before=before,
            after=self._snapshot(row),
            ip=ip,
        )
        await db.flush()

        if row.endpoint != old_endpoint:
            await self._delete_cache(redis, old_endpoint)
        await self._write_cache(redis, row)
        logger.info("Rate limit updated id=%s endpoint=%s", row.id, row.endpoint)
        peak = await self._current_peak(redis, row.endpoint, row.scope_type)
        return self._serialize(row, peak)

    async def delete_rate_limit(
        self,
        rate_limit_id: uuid.UUID,
        current_user: dict,
        ip: Optional[str],
        db: AsyncSession,
        redis: Redis,
    ) -> dict:
        row = await self._load(rate_limit_id, db)
        snapshot = self._snapshot(row)
        endpoint = row.endpoint
        await self._audit(
            db,
            current_user,
            AuditAction.RATE_LIMIT_DELETED.value,
            row.id,
            before=snapshot,
            after=None,
            ip=ip,
        )
        await db.delete(row)
        await db.flush()
        # drop the override so the route reverts to its hardcoded default.
        await self._delete_cache(redis, endpoint)
        logger.info("Rate limit deleted id=%s endpoint=%s", rate_limit_id, endpoint)
        return {"rate_limit_id": str(rate_limit_id), "deleted": True}

    # ── Redis: hot-path cache + live peak ────────────────────────────────────

    @staticmethod
    async def _write_cache(redis: Redis, row: RateLimitConfigs) -> None:
        await redis.set(
            f"{RATE_LIMIT_CONFIG_PREFIX}{row.endpoint}",
            json.dumps(
                {
                    "limit": row.request_limit,
                    "window_seconds": row.window_seconds,
                    "scope_type": row.scope_type,
                }
            ),
        )

    @staticmethod
    async def _delete_cache(redis: Redis, endpoint: str) -> None:
        await redis.delete(f"{RATE_LIMIT_CONFIG_PREFIX}{endpoint}")

    @staticmethod
    async def _current_peak(redis: Redis, endpoint: str, scope_type: str) -> int:
        """Highest live counter across subjects in the current window (best-effort,
        bounded scan). GLOBAL is a single key; PER_IP/PER_USER are scanned."""
        if scope_type == RateLimitScope.GLOBAL.value:
            val = await redis.get(
                rate_limit_counter_key(endpoint, scope_type, "global")
            )
            return int(val) if val else 0

        pattern = f"ratelimit:{endpoint}:{scope_type}:*"
        peak = 0
        cursor = 0
        for _ in range(_PEAK_SCAN_MAX_BATCHES):
            cursor, keys = await redis.scan(
                cursor, match=pattern, count=_PEAK_SCAN_COUNT
            )
            if keys:
                values = await redis.mget(keys)
                peak = max([peak] + [int(v) for v in values if v is not None])
            if cursor == 0:
                break
        return peak

    # ── Helpers ─────────────────────────────────────────────────────────────

    async def _ensure_endpoint_free(
        self, db: AsyncSession, endpoint: str, exclude_id: Optional[uuid.UUID]
    ) -> None:
        query = select(RateLimitConfigs.id).where(RateLimitConfigs.endpoint == endpoint)
        if exclude_id is not None:
            query = query.where(RateLimitConfigs.id != exclude_id)
        if (await db.execute(query)).first() is not None:
            raise RailMindException(
                code=ERR_RATE_LIMIT_DUPLICATE,
                message=f"A rate limit for '{endpoint}' already exists.",
                status_code=409,
            )

    async def _load(
        self, rate_limit_id: uuid.UUID, db: AsyncSession
    ) -> RateLimitConfigs:
        row = (
            await db.execute(
                select(RateLimitConfigs).where(RateLimitConfigs.id == rate_limit_id)
            )
        ).scalar_one_or_none()
        if row is None:
            raise RailMindException(
                code=ERR_RATE_LIMIT_NOT_FOUND,
                message="Rate limit not found.",
                status_code=404,
            )
        return row

    @staticmethod
    def _actor_uuid(current_user: dict):
        sub = current_user.get("sub")
        return uuid.UUID(sub) if sub else None

    @staticmethod
    def _snapshot(row: RateLimitConfigs) -> dict:
        return {f: getattr(row, f) for f in _AUDIT_SNAPSHOT_FIELDS}

    @staticmethod
    def _window_label(seconds: int) -> str:
        if seconds % 3600 == 0:
            n = seconds // 3600
            return f"{n} hour" if n == 1 else f"{n} hours"
        if seconds % 60 == 0:
            return f"{seconds // 60} min"
        return f"{seconds} sec"

    @staticmethod
    def _status(peak: int, limit: int) -> str:
        if limit <= 0 or peak >= limit:
            return STATUS_AT_CAP
        if peak >= NEAR_RATIO * limit:
            return STATUS_NEAR
        return STATUS_OK

    async def _audit(
        self, db, current_user, action, target_id, *, before, after, ip
    ) -> None:
        await audit_service.record(
            db,
            actor_id=current_user.get("sub"),
            actor_username=current_user.get("username"),
            action=action,
            target_type=AuditTargetType.RATE_LIMIT.value,
            target_id=target_id,
            before=before,
            after=after,
            ip=ip,
        )

    def _serialize(self, row: RateLimitConfigs, peak: int) -> RateLimitItemDTO:
        limit = row.request_limit
        return RateLimitItemDTO(
            rate_limit_id=str(row.id),
            endpoint=row.endpoint,
            window_seconds=row.window_seconds,
            window_label=self._window_label(row.window_seconds),
            limit=limit,
            scope_type=row.scope_type,
            scope_label=SCOPE_LABELS.get(row.scope_type, row.scope_type),
            current_peak=peak,
            peak_ratio=round(peak / limit, 4) if limit > 0 else 0.0,
            status=self._status(peak, limit),
            created_at=row.created_at,
        )
