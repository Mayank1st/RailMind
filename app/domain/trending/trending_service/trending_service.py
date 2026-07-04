import json
import logging
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from redis.asyncio import Redis
from sqlalchemy import String, cast, delete, desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from app.ai.prompts.trending_tagline_prompts import (
    TAGLINE_SYSTEM_INSTRUCTION,
    trending_tagline_prompt,
)
from app.db.models.popular_destinations import PopularDestinations
from app.db.models.search_events import SearchEvents
from app.db.models.train import Stations, TrainStations
from app.db.models.trending_routes import TrendingRoutes
from app.domain.fare.dto.fare_dto import FareEnquiryRequestDTO
from app.domain.fare.fare_service.fare_service import FareEnquiryService
from app.domain.train.dto.train_request_dto import SearchTrainDTO
from app.domain.train.train_service.train_service import TrainService
from app.domain.trending.constants.trending import (
    ERROR_CODE_TRENDING,
    POPULAR_DEST_LIMIT,
    TAGLINE_FALLBACKS,
    TAGLINE_MAX_LENGTH,
    TRENDING_FLEX_DAYS,
    TRENDING_LOOKBACK_DAYS,
    TRENDING_SEARCH_SIZE,
    TrendingDemandLevel,
)
from app.domain.trending.dto.trending_response_dto import (
    PopularDestinationResponseDTO,
    TrendingRouteResponseDTO,
    WeeklyPopularDestinationsResponseDTO,
    WeeklyTrendingResponseDTO,
)
from app.domain.trending.trending_service.city_image_service import city_image_service
from app.integrations.replicate_client import replicate_client
from app.integrations.replicate_models import MODEL1

logger = logging.getLogger(__name__)

_IST = ZoneInfo("Asia/Kolkata")

_LEVEL_ORDER = {
    TrendingDemandLevel.HIGH.value: 0,
    TrendingDemandLevel.MEDIUM.value: 1,
    TrendingDemandLevel.LOW.value: 2,
}


class TrendingService:
    def __init__(self) -> None:
        self._train = TrainService()
        self._fare = FareEnquiryService()

    # ── Weekly compute (celery beat, Sunday 23:59 IST) ────────────────────────

    async def compute_weekly_trending(self, db: AsyncSession, redis: Redis) -> int:
        """Computes and stores this week's cards. Returns cards written (0 when
        the week had no searches — previous week's cards are kept)."""
        now_ist = datetime.now(_IST)
        cutoff = now_ist - timedelta(days=TRENDING_LOOKBACK_DAYS)
        week_start = now_ist.date() - timedelta(days=TRENDING_LOOKBACK_DAYS - 1)

        searcher_identity = func.coalesce(
            cast(SearchEvents.user_id, String),
            SearchEvents.session_hash,
            cast(SearchEvents.id, String),
        )
        ranked = (
            await db.execute(
                select(
                    SearchEvents.source_station_id,
                    SearchEvents.destination_station_id,
                    func.count(func.distinct(searcher_identity)).label("search_count"),
                )
                .where(SearchEvents.searched_at >= cutoff)
                .group_by(
                    SearchEvents.source_station_id,
                    SearchEvents.destination_station_id,
                )
                .order_by(
                    desc("search_count"),
                    SearchEvents.source_station_id,
                    SearchEvents.destination_station_id,
                )
            )
        ).all()
        if not ranked:
            logger.info("trending: no searches in the last week — keeping old cards")
            return 0

        picks = self._pick_buckets(ranked)
        stations = await self._station_map(
            db,
            {r.source_station_id for _, r in picks}
            | {r.destination_station_id for _, r in picks},
        )

        cards: list[TrendingRoutes] = []
        for level, row in picks:
            src = stations.get(row.source_station_id)
            dst = stations.get(row.destination_station_id)
            if src is None or dst is None:
                continue  # station deleted mid-week — skip the card
            train = await self._route_card(
                db, redis, src.station_code, dst.station_code
            )
            cards.append(
                TrendingRoutes(
                    week_start=week_start,
                    demand_level=level,
                    source_station_id=row.source_station_id,
                    destination_station_id=row.destination_station_id,
                    source_station_code=src.station_code,
                    source_station_name=src.station_name,
                    destination_station_code=dst.station_code,
                    destination_station_name=dst.station_name,
                    train_number=train.get("train_number"),
                    train_name=train.get("train_name"),
                    avg_duration_minutes=train.get("avg_duration_minutes"),
                    min_fare=train.get("min_fare"),
                    search_count=int(row.search_count),
                )
            )
        if not cards:
            return 0

        await db.execute(
            delete(TrendingRoutes).where(TrendingRoutes.week_start == week_start)
        )
        db.add_all(cards)
        await db.commit()
        logger.info("trending: stored %s cards for week %s", len(cards), week_start)
        return len(cards)

    # ── Popular destinations ("Where India's heading", same Sunday job) ──────

    async def compute_popular_destinations(self, db: AsyncSession, redis: Redis) -> int:
        """Top POPULAR_DEST_LIMIT destinations by distinct searchers over the
        last week, each enriched with its top origin, corridor train count,
        representative train + cheapest fare, an LLM tagline and a carousel
        image (Supabase-cached, nano-banana-2 generated). Returns cards
        written (0 when the week had no searches — old cards kept)."""
        now_ist = datetime.now(_IST)
        cutoff = now_ist - timedelta(days=TRENDING_LOOKBACK_DAYS)
        week_start = now_ist.date() - timedelta(days=TRENDING_LOOKBACK_DAYS - 1)

        searcher_identity = func.coalesce(
            cast(SearchEvents.user_id, String),
            SearchEvents.session_hash,
            cast(SearchEvents.id, String),
        )
        top_destinations = (
            await db.execute(
                select(
                    SearchEvents.destination_station_id,
                    func.count(func.distinct(searcher_identity)).label("search_count"),
                )
                .where(SearchEvents.searched_at >= cutoff)
                .group_by(SearchEvents.destination_station_id)
                .order_by(desc("search_count"), SearchEvents.destination_station_id)
                .limit(POPULAR_DEST_LIMIT)
            )
        ).all()
        if not top_destinations:
            logger.info("popular-dest: no searches last week — keeping old cards")
            return 0

        # Top origin per destination (most distinct searchers on that corridor).
        origins: dict = {}
        for dest in top_destinations:
            origin_row = (
                await db.execute(
                    select(
                        SearchEvents.source_station_id,
                        func.count(func.distinct(searcher_identity)).label("cnt"),
                    )
                    .where(
                        SearchEvents.searched_at >= cutoff,
                        SearchEvents.destination_station_id
                        == dest.destination_station_id,
                    )
                    .group_by(SearchEvents.source_station_id)
                    .order_by(desc("cnt"), SearchEvents.source_station_id)
                    .limit(1)
                )
            ).first()
            origins[dest.destination_station_id] = origin_row.source_station_id

        stations = await self._station_map(db, set(origins) | set(origins.values()))

        # Build cards (best-effort enrichment, same policy as trending routes).
        cards: list[PopularDestinations] = []
        train_types: dict[str, str | None] = {}  # dest station name -> train_type
        for rank, dest in enumerate(top_destinations, start=1):
            dst = stations.get(dest.destination_station_id)
            src = stations.get(origins[dest.destination_station_id])
            if dst is None or src is None:
                continue  # station deleted mid-week — skip the card
            train = await self._route_card(
                db, redis, src.station_code, dst.station_code
            )
            train_types[dst.station_name] = train.get("train_type")
            cards.append(
                PopularDestinations(
                    week_start=week_start,
                    rank=rank,
                    destination_station_id=dst.id,
                    destination_station_code=dst.station_code,
                    destination_station_name=dst.station_name,
                    origin_station_id=src.id,
                    origin_station_code=src.station_code,
                    origin_station_name=src.station_name,
                    trains_count=await self._corridor_train_count(db, src.id, dst.id),
                    train_number=train.get("train_number"),
                    train_name=train.get("train_name"),
                    min_fare=train.get("min_fare"),
                    tagline=None,  # filled below (one batched Gemini call)
                    search_count=int(dest.search_count),
                )
            )
        if not cards:
            return 0

        taglines = await self._generate_taglines(cards, train_types)
        for card in cards:
            card.tagline = taglines.get(card.destination_station_name) or (
                TAGLINE_FALLBACKS.get(
                    (train_types.get(card.destination_station_name) or "").upper(),
                    TAGLINE_FALLBACKS["UNKNOWN"],
                )
            )

        # Carousel images — existing Supabase images reused, missing ones
        # generated via nano-banana-2; None on failure (card still renders).
        city_images = await city_image_service.get_city_images(
            [card.destination_station_name for card in cards]
        )
        for card in cards:
            card.image_url = city_images.get(card.destination_station_name)

        await db.execute(
            delete(PopularDestinations).where(
                PopularDestinations.week_start == week_start
            )
        )
        db.add_all(cards)
        await db.commit()
        logger.info("popular-dest: stored %s cards for week %s", len(cards), week_start)
        return len(cards)

    async def get_latest_popular_destinations(self, db: AsyncSession) -> dict:
        latest_week = (
            await db.execute(select(func.max(PopularDestinations.week_start)))
        ).scalar_one_or_none()
        if latest_week is None:
            return WeeklyPopularDestinationsResponseDTO(
                week_start=None, destinations=[]
            ).model_dump(mode="json")

        rows = (
            (
                await db.execute(
                    select(PopularDestinations)
                    .where(PopularDestinations.week_start == latest_week)
                    .order_by(PopularDestinations.rank)
                )
            )
            .scalars()
            .all()
        )
        destinations = [
            PopularDestinationResponseDTO(
                rank=r.rank,
                destination_station_code=r.destination_station_code,
                destination_station_name=r.destination_station_name,
                origin_station_code=r.origin_station_code,
                origin_station_name=r.origin_station_name,
                trains_count=r.trains_count,
                train_number=r.train_number,
                train_name=r.train_name,
                min_fare=float(r.min_fare) if r.min_fare is not None else None,
                tagline=r.tagline,
                image_url=r.image_url,
                search_count=r.search_count,
            )
            for r in rows
        ]
        return WeeklyPopularDestinationsResponseDTO(
            week_start=latest_week, destinations=destinations
        ).model_dump(mode="json")

    # ── Read path (public endpoint) ───────────────────────────────────────────

    async def get_latest_trending(self, db: AsyncSession) -> dict:
        latest_week = (
            await db.execute(select(func.max(TrendingRoutes.week_start)))
        ).scalar_one_or_none()
        if latest_week is None:
            return WeeklyTrendingResponseDTO(week_start=None, routes=[]).model_dump(
                mode="json"
            )

        rows = (
            (
                await db.execute(
                    select(TrendingRoutes).where(
                        TrendingRoutes.week_start == latest_week
                    )
                )
            )
            .scalars()
            .all()
        )
        rows.sort(key=lambda r: _LEVEL_ORDER.get(r.demand_level, len(_LEVEL_ORDER)))
        routes = [
            TrendingRouteResponseDTO(
                demand_level=r.demand_level,
                source_station_code=r.source_station_code,
                source_station_name=r.source_station_name,
                destination_station_code=r.destination_station_code,
                destination_station_name=r.destination_station_name,
                train_number=r.train_number,
                train_name=r.train_name,
                avg_duration_minutes=r.avg_duration_minutes,
                min_fare=float(r.min_fare) if r.min_fare is not None else None,
                search_count=r.search_count,
            )
            for r in rows
        ]
        return WeeklyTrendingResponseDTO(
            week_start=latest_week, routes=routes
        ).model_dump(mode="json")

    # ── Internals ─────────────────────────────────────────────────────────────

    @staticmethod
    def _pick_buckets(ranked: list) -> list[tuple[str, object]]:
        """One route per demand bucket from the count-ranked list: HIGH = top,
        MEDIUM = median rank, LOW = bottom. Degrades when fewer than 3 routes."""
        total = len(ranked)
        if total >= 3:
            return [
                (TrendingDemandLevel.HIGH.value, ranked[0]),
                (TrendingDemandLevel.MEDIUM.value, ranked[total // 2]),
                (TrendingDemandLevel.LOW.value, ranked[-1]),
            ]
        if total == 2:
            return [
                (TrendingDemandLevel.HIGH.value, ranked[0]),
                (TrendingDemandLevel.LOW.value, ranked[1]),
            ]
        return [(TrendingDemandLevel.HIGH.value, ranked[0])]

    @staticmethod
    async def _station_map(db: AsyncSession, station_ids: set) -> dict:
        rows = (
            (
                await db.execute(
                    select(Stations).where(Stations.id.in_(list(station_ids)))
                )
            )
            .scalars()
            .all()
        )
        return {s.id: s for s in rows}

    async def _route_card(
        self, db: AsyncSession, redis: Redis, from_code: str, to_code: str
    ) -> dict:
        """Representative train + avg duration + cheapest fare for one route.
        Best-effort — {} on any failure so the card still stores route + demand."""
        try:
            payload = SearchTrainDTO(
                fromStationCode=from_code,
                toStationCode=to_code,
                journey_date=datetime.now(_IST).date() + timedelta(days=1),
                flexible_dates=True,
                flex_days=TRENDING_FLEX_DAYS,
                size=TRENDING_SEARCH_SIZE,
            )
            result = await self._train.search_trains(payload, db)
        except Exception:
            logger.warning(
                "%s train lookup failed for %s->%s",
                ERROR_CODE_TRENDING,
                from_code,
                to_code,
            )
            return {}

        # Flex expansion repeats a train per date — keep first (requested-date-
        # first order) occurrence per train_number.
        trains: dict[str, dict] = {}
        for item in result.get("items", []):
            number = item.get("train_number")
            if number and number not in trains and item.get("duration_minutes"):
                trains[number] = item
        if not trains:
            return {}

        durations = [t["duration_minutes"] for t in trains.values()]
        representative = min(trains.values(), key=lambda t: t["duration_minutes"])
        card = {
            "train_number": representative.get("train_number"),
            "train_name": representative.get("train_name"),
            "train_type": representative.get("train_type"),
            "avg_duration_minutes": round(sum(durations) / len(durations)),
            "min_fare": await self._min_fare(
                db, redis, representative, from_code, to_code
            ),
        }
        return card

    @staticmethod
    async def _corridor_train_count(
        db: AsyncSession, origin_station_id, destination_station_id
    ) -> int | None:
        """Distinct trains whose route covers origin -> destination in order —
        the card's "· N trains". None on failure (card still renders)."""
        try:
            src_stop = aliased(TrainStations)
            dst_stop = aliased(TrainStations)
            count = (
                await db.execute(
                    select(func.count(func.distinct(src_stop.train_id)))
                    .join(dst_stop, dst_stop.train_id == src_stop.train_id)
                    .where(
                        src_stop.station_id == origin_station_id,
                        dst_stop.station_id == destination_station_id,
                        src_stop.sequence_number < dst_stop.sequence_number,
                    )
                )
            ).scalar_one()
            return int(count)
        except Exception:
            logger.warning("%s corridor train count failed", ERROR_CODE_TRENDING)
            return None

    async def _generate_taglines(
        self, cards: list, train_types: dict[str, str | None]
    ) -> dict[str, str]:
        """One batched LLM call -> {destination station name: tagline}.
        Empty dict on any failure — callers fall back to train-type taglines."""
        try:
            lines = "\n".join(
                f"- {c.destination_station_name} | "
                f"{train_types.get(c.destination_station_name) or 'UNKNOWN'}"
                for c in cards
            )
            text = await replicate_client(
                prompt=trending_tagline_prompt(destinations=lines),
                model=MODEL1,
                system_prompt=TAGLINE_SYSTEM_INSTRUCTION,
            )
            raw = (text or "").strip()
            if raw.startswith("```"):  # tolerate markdown-fenced JSON
                raw = raw.strip("`").removeprefix("json").strip()
            parsed = json.loads(raw)
            return {
                str(name): str(tagline)[:TAGLINE_MAX_LENGTH]
                for name, tagline in parsed.items()
                if isinstance(tagline, str) and tagline.strip()
            }
        except Exception:
            logger.warning(
                "%s LLM taglines failed — using train-type fallbacks",
                ERROR_CODE_TRENDING,
            )
            return {}

    async def _min_fare(
        self,
        db: AsyncSession,
        redis: Redis,
        train: dict,
        from_code: str,
        to_code: str,
    ) -> float | None:
        """Cheapest class total for the representative train — the card's
        "from ₹X" price. None on any failure."""
        try:
            payload = FareEnquiryRequestDTO(
                train_number=train["train_number"],
                source_station_code=from_code,
                destination_station_code=to_code,
                journey_date=date.fromisoformat(train["journey_date"]),
            )
            data, _ = await self._fare.get_fare_enquiry(payload, db, redis)
            fares = data.get("fares") or []
            return min(float(f["total_fare"]) for f in fares) if fares else None
        except Exception:
            logger.warning(
                "%s fare lookup failed for train %s %s->%s",
                ERROR_CODE_TRENDING,
                train.get("train_number"),
                from_code,
                to_code,
            )
            return None


trending_service = TrendingService()
