import json
from datetime import date, datetime, timezone
from typing import Optional

from redis.asyncio import Redis
from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from app.domain.search_history.constants.search_history import (
    RECENT_SEARCH_CACHE_PREFIX,
    RECENT_SEARCH_CACHE_TTL,
    RECENT_SEARCH_MAX,
)
from app.db.models.search_events import SearchEvents
from app.db.models.search_histories import SearchHistories
from app.db.models.train import Stations
from app.domain.search_history.dto.search_history_response_dto import (
    RecentSearchDTO,
    StationBriefDTO,
)


class SearchHistoryService:
    # ── Write path (called from Celery task) ──────────────────────────────────

    async def log_search(
        self,
        db: AsyncSession,
        redis: Redis,
        user_id: str,
        from_code: str,
        to_code: str,
        journey_date: Optional[date] = None,
        train_class: Optional[str] = None,
        quota: Optional[str] = None,
    ) -> bool:
        codes = await self._resolve_station_ids(db, from_code, to_code)
        if codes is None:
            return False
        src_id, dst_id = codes

        now = datetime.now(timezone.utc)

        stmt = (
            pg_insert(SearchHistories)
            .values(
                user_id=user_id,
                source_station_id=src_id,
                destination_station_id=dst_id,
                journey_date=journey_date,
                train_class=train_class,
                quota=quota,
                searched_at=now,
            )
            .on_conflict_do_update(
                index_elements=[
                    "user_id",
                    "source_station_id",
                    "destination_station_id",
                ],
                set_={
                    "journey_date": journey_date,
                    "train_class": train_class,
                    "quota": quota,
                    "searched_at": now,
                    "updated_at": now,
                },
            )
        )
        await db.execute(stmt)
        await self._trim_to_cap(db, user_id)
        await db.commit()

        await redis.delete(f"{RECENT_SEARCH_CACHE_PREFIX}{user_id}")
        return True

    async def log_search_event(
        self,
        db: AsyncSession,
        user_id: Optional[str],
        session_hash: Optional[str],
        from_code: str,
        to_code: str,
        journey_date: Optional[date] = None,
        train_class: Optional[str] = None,
        quota: Optional[str] = None,
    ) -> bool:
        """Append-only analytics event — every search, guests included. Identity
        for downstream dedupe is user_id (logged-in) or session_hash (guest)."""
        codes = await self._resolve_station_ids(db, from_code, to_code)
        if codes is None:
            return False
        src_id, dst_id = codes

        db.add(
            SearchEvents(
                user_id=user_id,
                session_hash=session_hash,
                source_station_id=src_id,
                destination_station_id=dst_id,
                journey_date=journey_date,
                train_class=train_class,
                quota=quota,
            )
        )
        await db.commit()
        return True

    async def _trim_to_cap(self, db: AsyncSession, user_id: str) -> None:
        """Keep only the RECENT_SEARCH_MAX most recent rows for this user."""
        stale = (
            select(SearchHistories.id)
            .where(SearchHistories.user_id == user_id)
            .order_by(SearchHistories.searched_at.desc())
            .offset(RECENT_SEARCH_MAX)
        )
        await db.execute(delete(SearchHistories).where(SearchHistories.id.in_(stale)))

    @staticmethod
    async def _resolve_station_ids(
        db: AsyncSession, from_code: str, to_code: str
    ) -> Optional[tuple]:
        rows = (
            await db.execute(
                select(Stations.id, Stations.station_code).where(
                    Stations.station_code.in_([from_code.upper(), to_code.upper()])
                )
            )
        ).all()
        by_code = {r.station_code: r.id for r in rows}
        src_id = by_code.get(from_code.upper())
        dst_id = by_code.get(to_code.upper())
        if not src_id or not dst_id or src_id == dst_id:
            return None
        return src_id, dst_id

    # ── Read path (GET endpoint) ──────────────────────────────────────────────

    async def get_recent_searches(
        self,
        db: AsyncSession,
        redis: Redis,
        user_id: str,
        limit: int,
    ) -> list[dict]:
        cache_key = f"{RECENT_SEARCH_CACHE_PREFIX}{user_id}"
        cached = await redis.get(cache_key)
        if cached is not None:
            return json.loads(cached)[:limit]

        SRC = aliased(Stations)
        DST = aliased(Stations)
        stmt = (
            select(
                SearchHistories.id,
                SRC.station_code.label("src_code"),
                SRC.station_name.label("src_name"),
                DST.station_code.label("dst_code"),
                DST.station_name.label("dst_name"),
                SearchHistories.journey_date,
                SearchHistories.train_class,
                SearchHistories.quota,
                SearchHistories.searched_at,
            )
            .join(SRC, SRC.id == SearchHistories.source_station_id)
            .join(DST, DST.id == SearchHistories.destination_station_id)
            .where(SearchHistories.user_id == user_id)
            .order_by(SearchHistories.searched_at.desc())
            .limit(RECENT_SEARCH_MAX)
        )
        rows = (await db.execute(stmt)).all()

        items = [
            RecentSearchDTO(
                id=row.id,
                source=StationBriefDTO(code=row.src_code, name=row.src_name),
                destination=StationBriefDTO(code=row.dst_code, name=row.dst_name),
                journey_date=row.journey_date,
                train_class=row.train_class,
                quota=row.quota,
                searched_at=row.searched_at,
            ).model_dump(mode="json")
            for row in rows
        ]

        # Cache the full capped list; slice per-request so different `limit`
        # values share one cache entry.
        await redis.setex(cache_key, RECENT_SEARCH_CACHE_TTL, json.dumps(items))
        return items[:limit]

    # ── Housekeeping (daily Celery beat) ──────────────────────────────────────

    async def cleanup(self, db: AsyncSession) -> int:
        """
        Drop rows whose journey_date has passed (only relevant once date-based
        search exists; no-op while journey_date is null). Per-user capping is
        handled inline in log_search.
        """
        result = await db.execute(
            delete(SearchHistories).where(
                SearchHistories.journey_date.is_not(None),
                SearchHistories.journey_date < date.today(),
            )
        )
        await db.commit()
        return result.rowcount or 0


search_history_service = SearchHistoryService()
