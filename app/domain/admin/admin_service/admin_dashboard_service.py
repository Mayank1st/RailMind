import json
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from redis.asyncio import Redis
from sqlalchemy import delete, func, select, tuple_
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.booking import Bookings
from app.db.models.daily_seat_occupancy import DailySeatOccupancies
from app.db.models.payment import Payments
from app.db.models.train import SeatInventories, Stations
from app.domain.admin.constants.admin_dashboard import (
    CANCELLED_STATUSES,
    CONFIRMED_BOOKING_STATUSES,
    EXCLUDED_BOOKING_STATUSES,
    IST_TIMEZONE_NAME,
    OVERVIEW_CACHE_KEY_PREFIX,
    OVERVIEW_CACHE_TTL_SECONDS,
    RANGE_BUCKETS,
    TOP_ROUTES_LIMIT,
    WAITLISTED_BOOKING_STATUS,
)
from app.domain.admin.dto.admin_dashboard_response_dto import (
    BookingsVolumePointDTO,
    MetricKpiDTO,
    OverviewMetricsResponseDTO,
    RevenueByClassDTO,
    TopRouteDTO,
)
from app.domain.payment.constants.payment import PaymentStatus

_IST = ZoneInfo(IST_TIMEZONE_NAME)
_UTC = timezone.utc


@dataclass(frozen=True)
class _MetricsWindow:
    """Resolved time bounds for one Overview request. Query rows are bucketed
    with `to_char(timezone('Asia/Kolkata', ts), sql_fmt)` — a driver-stable text
    key — and matched against `bucket_keys` so empty slots fill with zero without
    depending on how asyncpg decodes a timestamp's tz."""

    bucket_kind: str  # "hour" | "day"
    bucket_starts: list[datetime]  # naive IST, one per sparkline point (label source)
    bucket_keys: list[str]  # to_char text key per bucket, aligned with bucket_starts
    sql_fmt: str  # to_char format used in the bucketed queries
    day_divisor: int  # denominator for the "/day" KPIs
    cur_start_utc: datetime
    cur_end_utc: datetime
    prev_start_utc: datetime
    prev_end_utc: datetime
    cur_start_date: date
    cur_end_date: date
    prev_start_date: date
    prev_end_date: date
    num_days: int


class AdminDashboardService:
    """Read-only aggregations behind the admin console Overview page. Every
    widget is driven by a single `range` (24h / 7d / 30d); KPI deltas compare
    the window against the immediately-preceding equal-length window."""

    async def get_overview(
        self, range_key: str, db: AsyncSession, redis: Redis
    ) -> dict:
        cache_key = f"{OVERVIEW_CACHE_KEY_PREFIX}{range_key}"
        cached = await redis.get(cache_key)
        if cached:
            return json.loads(cached)

        window = self._resolve_window(range_key)

        by_bucket = await self._bookings_by_bucket(db, window)
        prev_counted, prev_cancelled = await self._prev_booking_totals(db, window)
        revenue_by_bucket = await self._revenue_by_bucket(db, window)
        prev_revenue = await self._prev_revenue(db, window)
        # One scan covers both current + previous windows — see _occupancy_by_day.
        occ_by_day = await self._occupancy_by_day(db, window)

        data = OverviewMetricsResponseDTO(
            range=range_key,
            generated_at=datetime.now(_UTC),
            bookings_per_day=self._bookings_kpi(window, by_bucket, prev_counted),
            revenue=self._revenue_kpi(window, revenue_by_bucket, prev_revenue),
            seat_occupancy=self._occupancy_kpi(window, occ_by_day),
            cancellation_rate=self._cancellation_kpi(
                window, by_bucket, prev_counted, prev_cancelled
            ),
            bookings_volume=self._bookings_volume(window, by_bucket),
            revenue_by_class=await self._revenue_by_class(db, window),
            top_routes=await self._top_routes(db, window),
        ).model_dump(mode="json")

        await redis.setex(cache_key, OVERVIEW_CACHE_TTL_SECONDS, json.dumps(data))
        return data

    # ── Window resolution ─────────────────────────────────────────────────────

    @staticmethod
    def _resolve_window(range_key: str) -> _MetricsWindow:
        kind, count, divisor = RANGE_BUCKETS[range_key]
        now_ist = datetime.now(_IST)

        if kind == "hour":
            anchor = now_ist.replace(minute=0, second=0, microsecond=0)
            starts_aware = [
                anchor - timedelta(hours=count - 1 - i) for i in range(count)
            ]
            sql_fmt, py_fmt = "YYYY-MM-DD HH24", "%Y-%m-%d %H"
        else:
            anchor = now_ist.replace(hour=0, minute=0, second=0, microsecond=0)
            starts_aware = [
                anchor - timedelta(days=count - 1 - i) for i in range(count)
            ]
            sql_fmt, py_fmt = "YYYY-MM-DD", "%Y-%m-%d"

        naive_starts = [s.replace(tzinfo=None) for s in starts_aware]
        cur_start_utc = starts_aware[0].astimezone(_UTC)
        cur_end_utc = now_ist.astimezone(_UTC)
        span = cur_end_utc - cur_start_utc

        cur_start_date = starts_aware[0].date()
        cur_end_date = now_ist.date()
        num_days = (cur_end_date - cur_start_date).days + 1
        prev_end_date = cur_start_date - timedelta(days=1)

        return _MetricsWindow(
            bucket_kind=kind,
            bucket_starts=naive_starts,
            bucket_keys=[s.strftime(py_fmt) for s in naive_starts],
            sql_fmt=sql_fmt,
            day_divisor=divisor,
            cur_start_utc=cur_start_utc,
            cur_end_utc=cur_end_utc,
            prev_start_utc=cur_start_utc - span,
            prev_end_utc=cur_start_utc,
            cur_start_date=cur_start_date,
            cur_end_date=cur_end_date,
            prev_start_date=prev_end_date - timedelta(days=num_days - 1),
            prev_end_date=prev_end_date,
            num_days=num_days,
        )

    # ── Booking rollups (one query powers volume + bookings KPI + cancels) ────

    @staticmethod
    async def _bookings_by_bucket(db: AsyncSession, window: _MetricsWindow) -> dict:
        bucket = func.to_char(
            func.timezone(IST_TIMEZONE_NAME, Bookings.booked_at), window.sql_fmt
        ).label("bucket")
        rows = (
            await db.execute(
                select(
                    bucket,
                    func.count()
                    .filter(Bookings.booking_status.not_in(EXCLUDED_BOOKING_STATUSES))
                    .label("counted"),
                    func.count()
                    .filter(Bookings.booking_status.in_(CONFIRMED_BOOKING_STATUSES))
                    .label("confirmed"),
                    func.count()
                    .filter(Bookings.booking_status == WAITLISTED_BOOKING_STATUS)
                    .label("waitlist"),
                    func.count()
                    .filter(Bookings.booking_status.in_(CANCELLED_STATUSES))
                    .label("cancelled"),
                )
                .where(
                    Bookings.booked_at >= window.cur_start_utc,
                    Bookings.booked_at <= window.cur_end_utc,
                )
                .group_by(bucket)
            )
        ).all()
        return {r.bucket: r for r in rows}

    @staticmethod
    async def _prev_booking_totals(
        db: AsyncSession, window: _MetricsWindow
    ) -> tuple[int, int]:
        row = (
            await db.execute(
                select(
                    func.count().filter(
                        Bookings.booking_status.not_in(EXCLUDED_BOOKING_STATUSES)
                    ),
                    func.count().filter(
                        Bookings.booking_status.in_(CANCELLED_STATUSES)
                    ),
                ).where(
                    Bookings.booked_at >= window.prev_start_utc,
                    Bookings.booked_at < window.prev_end_utc,
                )
            )
        ).one()
        return int(row[0] or 0), int(row[1] or 0)

    def _bookings_kpi(
        self, window: _MetricsWindow, by_bucket: dict, prev_counted: int
    ) -> MetricKpiDTO:
        spark = [
            float(getattr(by_bucket.get(k), "counted", 0) or 0)
            for k in window.bucket_keys
        ]
        cur_total = sum(spark)
        value = cur_total / window.day_divisor
        prev_value = prev_counted / window.day_divisor
        return MetricKpiDTO(
            value=round(value),
            delta_pct=self._pct_delta(value, prev_value),
            spark=spark,
        )

    def _cancellation_kpi(
        self,
        window: _MetricsWindow,
        by_bucket: dict,
        prev_counted: int,
        prev_cancelled: int,
    ) -> MetricKpiDTO:
        spark = []
        cur_counted = 0
        cur_cancelled = 0
        for k in window.bucket_keys:
            row = by_bucket.get(k)
            counted = int(getattr(row, "counted", 0) or 0)
            cancelled = int(getattr(row, "cancelled", 0) or 0)
            cur_counted += counted
            cur_cancelled += cancelled
            spark.append(self._rate(cancelled, counted))
        value = self._rate(cur_cancelled, cur_counted)
        prev_value = self._rate(prev_cancelled, prev_counted)
        return MetricKpiDTO(
            value=value, delta_pct=self._pct_delta(value, prev_value), spark=spark
        )

    @staticmethod
    def _bookings_volume(
        window: _MetricsWindow, by_bucket: dict
    ) -> list[BookingsVolumePointDTO]:
        points = []
        for start, key in zip(window.bucket_starts, window.bucket_keys):
            row = by_bucket.get(key)
            points.append(
                BookingsVolumePointDTO(
                    bucket=start.isoformat(),
                    confirmed=int(getattr(row, "confirmed", 0) or 0),
                    waitlist=int(getattr(row, "waitlist", 0) or 0),
                )
            )
        return points

    # ── Revenue ───────────────────────────────────────────────────────────────

    @staticmethod
    async def _revenue_by_bucket(db: AsyncSession, window: _MetricsWindow) -> dict:
        bucket = func.to_char(
            func.timezone(IST_TIMEZONE_NAME, Payments.paid_at), window.sql_fmt
        ).label("bucket")
        rows = (
            await db.execute(
                select(bucket, func.sum(Payments.amount).label("revenue"))
                .where(
                    Payments.payment_status == PaymentStatus.SUCCESS,
                    Payments.paid_at >= window.cur_start_utc,
                    Payments.paid_at <= window.cur_end_utc,
                )
                .group_by(bucket)
            )
        ).all()
        return {r.bucket: float(r.revenue or 0) for r in rows}

    @staticmethod
    async def _prev_revenue(db: AsyncSession, window: _MetricsWindow) -> float:
        total = (
            await db.execute(
                select(func.sum(Payments.amount)).where(
                    Payments.payment_status == PaymentStatus.SUCCESS,
                    Payments.paid_at >= window.prev_start_utc,
                    Payments.paid_at < window.prev_end_utc,
                )
            )
        ).scalar_one_or_none()
        return float(total or 0)

    def _revenue_kpi(
        self, window: _MetricsWindow, by_bucket: dict, prev_revenue: float
    ) -> MetricKpiDTO:
        spark = [round(by_bucket.get(k, 0.0), 2) for k in window.bucket_keys]
        value = round(sum(spark), 2)
        return MetricKpiDTO(
            value=value,
            delta_pct=self._pct_delta(value, prev_revenue),
            spark=spark,
        )

    async def _revenue_by_class(
        self, db: AsyncSession, window: _MetricsWindow
    ) -> list[RevenueByClassDTO]:
        rows = (
            await db.execute(
                select(
                    Bookings.train_class,
                    func.sum(Payments.amount).label("revenue"),
                )
                .select_from(Payments)
                .join(Bookings, Payments.booking_id == Bookings.id)
                .where(
                    Payments.payment_status == PaymentStatus.SUCCESS,
                    Payments.paid_at >= window.cur_start_utc,
                    Payments.paid_at <= window.cur_end_utc,
                )
                .group_by(Bookings.train_class)
            )
        ).all()
        total = sum(float(r.revenue or 0) for r in rows)
        result = [
            RevenueByClassDTO(
                train_class=r.train_class,
                revenue=round(float(r.revenue or 0), 2),
                share_pct=self._rate(float(r.revenue or 0), total),
            )
            for r in rows
        ]
        result.sort(key=lambda c: c.revenue, reverse=True)
        return result

    # ── Occupancy (journeys departing in-window, keyed by journey_date) ───────

    @staticmethod
    async def _occupancy_by_day(db: AsyncSession, window: _MetricsWindow) -> dict:
        """Reads the precomputed `daily_seat_occupancies` rollup (a handful of
        rows) instead of scanning the multi-million-row seat_inventories table.
        The rollup is refreshed off the request path by a celery-beat task
        (`dashboard_tasks.task_refresh_daily_occupancy`). Covers both the current
        and previous windows in one range read for the KPI delta."""
        rows = (
            await db.execute(
                select(
                    DailySeatOccupancies.journey_date,
                    DailySeatOccupancies.total_confirmed_seats,
                    DailySeatOccupancies.booked_confirmed_seats,
                ).where(
                    DailySeatOccupancies.journey_date >= window.prev_start_date,
                    DailySeatOccupancies.journey_date <= window.cur_end_date,
                )
            )
        ).all()
        return {
            r.journey_date: (
                int(r.total_confirmed_seats or 0),
                int(r.booked_confirmed_seats or 0),
            )
            for r in rows
        }

    async def refresh_daily_occupancy(self, db: AsyncSession) -> int:
        """Recompute the whole daily-occupancy rollup from seat_inventories and
        replace it. This is the one place that pays the big seq scan — run it on
        a schedule, never on a request. Returns the number of days written."""
        booked = SeatInventories.total_confirmed_seats - (
            SeatInventories.available_confirmed_seats
        )
        rows = (
            await db.execute(
                select(
                    SeatInventories.journey_date,
                    func.sum(SeatInventories.total_confirmed_seats).label("total"),
                    func.sum(booked).label("booked"),
                ).group_by(SeatInventories.journey_date)
            )
        ).all()

        await db.execute(delete(DailySeatOccupancies))
        db.add_all(
            [
                DailySeatOccupancies(
                    journey_date=r.journey_date,
                    total_confirmed_seats=int(r.total or 0),
                    booked_confirmed_seats=int(r.booked or 0),
                )
                for r in rows
            ]
        )
        await db.commit()
        return len(rows)

    def _occupancy_kpi(self, window: _MetricsWindow, occ_by_day: dict) -> MetricKpiDTO:
        spark = []
        cur_total = cur_booked = 0
        day = window.cur_start_date
        while day <= window.cur_end_date:
            total, booked = occ_by_day.get(day, (0, 0))
            cur_total += total
            cur_booked += booked
            spark.append(self._rate(booked, total))
            day += timedelta(days=1)

        prev_total = prev_booked = 0
        day = window.prev_start_date
        while day <= window.prev_end_date:
            total, booked = occ_by_day.get(day, (0, 0))
            prev_total += total
            prev_booked += booked
            day += timedelta(days=1)

        value = self._rate(cur_booked, cur_total)
        prev_value = self._rate(prev_booked, prev_total)
        return MetricKpiDTO(
            value=value, delta_pct=self._pct_delta(value, prev_value), spark=spark
        )

    # ── Top routes (busiest corridors by booking volume) ──────────────────────

    async def _top_routes(
        self, db: AsyncSession, window: _MetricsWindow
    ) -> list[TopRouteDTO]:
        pair_rows = (
            await db.execute(
                select(
                    Bookings.source_station_id,
                    Bookings.destination_station_id,
                    func.count().label("bookings"),
                )
                .where(
                    Bookings.booked_at >= window.cur_start_utc,
                    Bookings.booked_at <= window.cur_end_utc,
                    Bookings.booking_status.not_in(EXCLUDED_BOOKING_STATUSES),
                )
                .group_by(Bookings.source_station_id, Bookings.destination_station_id)
                .order_by(func.count().desc())
                .limit(TOP_ROUTES_LIMIT)
            )
        ).all()
        if not pair_rows:
            return []

        pairs = [(r.source_station_id, r.destination_station_id) for r in pair_rows]
        revenue = await self._route_revenue(db, window, pairs)
        route_trains = await self._route_trains(db, window, pairs)
        train_stats = await self._train_inventory_stats(
            db, window, {t for trains in route_trains.values() for t in trains}
        )
        stations = await self._station_map(db, {sid for pair in pairs for sid in pair})

        routes = []
        for r in pair_rows:
            src = stations.get(r.source_station_id)
            dst = stations.get(r.destination_station_id)
            if src is None or dst is None:
                continue  # station deleted since booking — skip the row
            trains = route_trains.get(
                (r.source_station_id, r.destination_station_id), set()
            )
            total = sum(train_stats.get(t, (0, 0, 0))[0] for t in trains)
            booked = sum(train_stats.get(t, (0, 0, 0))[1] for t in trains)
            wl_depth = max(
                (train_stats.get(t, (0, 0, 0))[2] for t in trains), default=0
            )
            routes.append(
                TopRouteDTO(
                    source_code=src.station_code,
                    source_city=src.city,
                    destination_code=dst.station_code,
                    destination_city=dst.city,
                    trains_count=len(trains),
                    bookings=int(r.bookings),
                    occupancy_pct=self._rate(booked, total),
                    wl_depth=wl_depth,
                    revenue=round(
                        revenue.get(
                            (r.source_station_id, r.destination_station_id), 0.0
                        ),
                        2,
                    ),
                )
            )
        return routes

    @staticmethod
    async def _route_revenue(
        db: AsyncSession, window: _MetricsWindow, pairs: list[tuple]
    ) -> dict:
        rows = (
            await db.execute(
                select(
                    Bookings.source_station_id,
                    Bookings.destination_station_id,
                    func.sum(Payments.amount).label("revenue"),
                )
                .select_from(Bookings)
                .join(Payments, Payments.booking_id == Bookings.id)
                .where(
                    Bookings.booked_at >= window.cur_start_utc,
                    Bookings.booked_at <= window.cur_end_utc,
                    Payments.payment_status == PaymentStatus.SUCCESS,
                    tuple_(
                        Bookings.source_station_id, Bookings.destination_station_id
                    ).in_(pairs),
                )
                .group_by(Bookings.source_station_id, Bookings.destination_station_id)
            )
        ).all()
        return {
            (r.source_station_id, r.destination_station_id): float(r.revenue or 0)
            for r in rows
        }

    @staticmethod
    async def _route_trains(
        db: AsyncSession, window: _MetricsWindow, pairs: list[tuple]
    ) -> dict:
        rows = (
            await db.execute(
                select(
                    Bookings.source_station_id,
                    Bookings.destination_station_id,
                    Bookings.train_id,
                )
                .where(
                    Bookings.booked_at >= window.cur_start_utc,
                    Bookings.booked_at <= window.cur_end_utc,
                    tuple_(
                        Bookings.source_station_id, Bookings.destination_station_id
                    ).in_(pairs),
                )
                .distinct()
            )
        ).all()
        route_trains: dict = {}
        for r in rows:
            key = (r.source_station_id, r.destination_station_id)
            route_trains.setdefault(key, set()).add(r.train_id)
        return route_trains

    @staticmethod
    async def _train_inventory_stats(
        db: AsyncSession, window: _MetricsWindow, train_ids: set
    ) -> dict:
        """Per-train (total_seats, booked_seats, deepest_waitlist) over the
        window's journey dates — the corridor occupancy + WL-depth source."""
        if not train_ids:
            return {}
        booked = SeatInventories.total_confirmed_seats - (
            SeatInventories.available_confirmed_seats
        )
        rows = (
            await db.execute(
                select(
                    SeatInventories.train_id,
                    func.sum(SeatInventories.total_confirmed_seats).label("total"),
                    func.sum(booked).label("booked"),
                    func.max(SeatInventories.wl_count).label("wl"),
                )
                .where(
                    SeatInventories.train_id.in_(list(train_ids)),
                    SeatInventories.journey_date >= window.cur_start_date,
                    SeatInventories.journey_date <= window.cur_end_date,
                )
                .group_by(SeatInventories.train_id)
            )
        ).all()
        return {
            r.train_id: (int(r.total or 0), int(r.booked or 0), int(r.wl or 0))
            for r in rows
        }

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

    # ── Numeric helpers ───────────────────────────────────────────────────────

    @staticmethod
    def _rate(numerator: float, denominator: float) -> float:
        if denominator <= 0:
            return 0.0
        return round(numerator / denominator * 100, 1)

    @staticmethod
    def _pct_delta(current: float, previous: float) -> float | None:
        if previous == 0:
            return None
        return round((current - previous) / previous * 100, 1)
