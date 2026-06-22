from __future__ import annotations

import uuid

from sqlalchemy import and_, distinct, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from app.config import settings
from app.db.models.booking import BookingPassengers, Bookings
from app.db.models.passengers import Passengers
from app.db.models.train import Stations, Trains, TrainStations
from app.db.models.user_behavior_logs import UserActionType, UserBehaviorLogs
from app.domain.autofill.constants.autofill import (
    CONFIDENCE_DECIMALS,
    DEFAULT_BERTH,
    DEFAULT_CONFIDENCE,
    DEFAULT_QUOTA,
    DEFAULT_TRAIN_CLASS,
    COLD_START_MAX_BOOKINGS,
    PASSENGER_SUGGESTION_LIMIT,
    AutofillSource,
    DistanceBucket,
    bucket_bounds,
    bucket_for_distance,
)


class AutofillRulesService:
    """Level-1 (rules) Smart Form Autofill.

    Cold-start guard (<= COLD_START_MAX_BOOKINGS bookings) -> defaults. Otherwise
    suggest each field from booking history using "mode within distance bucket"
    for the class, and frequency mode for quota / co-passengers / berth. Every
    request is logged to user_behavior_logs so suggested-vs-actual pairs become
    Level-2 training data.
    """

    async def suggest_autofill(
        self,
        db: AsyncSession,
        user_id: str,
        train_number: str,
        source_station_code: str,
        destination_station_code: str,
    ) -> dict:
        result = await self.build_suggestion(
            db, user_id, train_number, source_station_code, destination_station_code
        )
        await self._log_suggestion(
            db,
            uuid.UUID(user_id),
            train_number,
            source_station_code,
            destination_station_code,
            result,
        )
        return result

    async def build_suggestion(
        self,
        db: AsyncSession,
        user_id: str,
        train_number: str,
        source_station_code: str,
        destination_station_code: str,
    ) -> dict:
        """Build the Level-1 suggestion dict WITHOUT logging — reused by the
        Level-2 model path for the quota / passenger / distance scaffold."""
        uid = uuid.UUID(user_id)

        booking_count = await self._booking_count(db, uid)
        journey_km = await self._journey_distance_km(
            db, train_number, source_station_code, destination_station_code
        )
        bucket = bucket_for_distance(journey_km) if journey_km is not None else None

        if booking_count <= COLD_START_MAX_BOOKINGS:
            return await self._defaults(db, uid, booking_count, journey_km, bucket)
        return await self._from_history(db, uid, booking_count, journey_km, bucket)

    async def count_user_bookings(self, db: AsyncSession, user_id: str) -> int:
        return await self._booking_count(db, uuid.UUID(user_id))

    async def favourite_train(
        self,
        db: AsyncSession,
        user_id: str,
        source_station_code: str,
        destination_station_code: str,
    ) -> dict | None:
        """Most-booked train on this exact route (plain history count, not ML).
        Depends only on user + route — independent of any chosen train_number.
        Returns None when the user has no prior bookings on the route."""
        uid = uuid.UUID(user_id)
        src_st = aliased(Stations)
        dst_st = aliased(Stations)
        stmt = (
            select(
                Trains.train_number,
                Trains.train_name,
                func.count().label("cnt"),
            )
            .select_from(Bookings)
            .join(Trains, Trains.id == Bookings.train_id)
            .join(
                src_st,
                and_(
                    src_st.id == Bookings.source_station_id,
                    src_st.station_code == source_station_code,
                ),
            )
            .join(
                dst_st,
                and_(
                    dst_st.id == Bookings.destination_station_id,
                    dst_st.station_code == destination_station_code,
                ),
            )
            .where(Bookings.user_id == uid)
            .group_by(Trains.train_number, Trains.train_name)
            .order_by(func.count().desc())
            .limit(1)
        )
        row = (await db.execute(stmt)).first()
        if row is None:
            return None
        return {
            "train_number": row.train_number,
            "train_name": row.train_name,
            "previous_booking_count": int(row.cnt),
        }

    def empty_suggestion(self, booking_count: int) -> dict:
        """Autofill scaffold with no class/berth prediction — used when no
        train_number is given (only the favourite_train block is meaningful)."""
        return {
            "train_class": {"value": None, "confidence": DEFAULT_CONFIDENCE},
            "quota": {"value": None, "confidence": DEFAULT_CONFIDENCE},
            "passengers": [],
            "source": AutofillSource.DEFAULTS.value,
            "distance_bucket": None,
            "journey_distance_km": None,
            "booking_count": booking_count,
            "based_on_bookings": 0,
            "auto_fill": False,
        }

    # ── History rules ─────────────────────────────────────────────────────────

    async def _from_history(
        self,
        db: AsyncSession,
        uid: uuid.UUID,
        booking_count: int,
        journey_km: int | None,
        bucket: DistanceBucket | None,
    ) -> dict:
        train_class, class_conf, based_on = await self._class_in_bucket(db, uid, bucket)
        quota_value, quota_conf = await self._mode_quota(db, uid, booking_count)
        passengers = await self._enriched_passengers(db, uid, booking_count)

        return {
            "train_class": {"value": train_class, "confidence": class_conf},
            "quota": {"value": quota_value, "confidence": quota_conf},
            "passengers": passengers,
            "source": AutofillSource.HISTORY.value,
            "distance_bucket": bucket.value if bucket else None,
            "journey_distance_km": journey_km,
            "booking_count": booking_count,
            "based_on_bookings": based_on,
            "auto_fill": class_conf >= settings.AI_CONFIDENCE_THRESHOLD,
        }

    async def _defaults(
        self,
        db: AsyncSession,
        uid: uuid.UUID,
        booking_count: int,
        journey_km: int | None,
        bucket: DistanceBucket | None,
    ) -> dict:
        primary = await self._primary_passenger(db, uid)
        passengers = (
            [
                {
                    "passenger_id": str(primary["id"]),
                    "full_name": primary["full_name"],
                    "age": primary["age"],
                    "gender": primary["gender"],
                    "berth": {"value": DEFAULT_BERTH, "confidence": DEFAULT_CONFIDENCE},
                    "confidence": DEFAULT_CONFIDENCE,
                }
            ]
            if primary
            else []
        )
        return {
            "train_class": {
                "value": DEFAULT_TRAIN_CLASS,
                "confidence": DEFAULT_CONFIDENCE,
            },
            "quota": {"value": DEFAULT_QUOTA, "confidence": DEFAULT_CONFIDENCE},
            "passengers": passengers,
            "source": AutofillSource.DEFAULTS.value,
            "distance_bucket": bucket.value if bucket else None,
            "journey_distance_km": journey_km,
            "booking_count": booking_count,
            "based_on_bookings": 0,
            "auto_fill": False,
        }

    # ── Field queries ─────────────────────────────────────────────────────────

    async def _booking_count(self, db: AsyncSession, uid: uuid.UUID) -> int:
        stmt = select(func.count()).select_from(Bookings).where(Bookings.user_id == uid)
        return int((await db.execute(stmt)).scalar_one())

    async def _journey_distance_km(
        self,
        db: AsyncSession,
        train_number: str,
        source_station_code: str,
        destination_station_code: str,
    ) -> int | None:
        """Distance (km) between source and destination on the given train, from
        train_stations cumulative distance. None if the route can't be resolved."""
        src_ts = aliased(TrainStations)
        dst_ts = aliased(TrainStations)
        src_st = aliased(Stations)
        dst_st = aliased(Stations)
        stmt = (
            select((dst_ts.distance_km - src_ts.distance_km))
            .select_from(Trains)
            .join(src_ts, src_ts.train_id == Trains.id)
            .join(
                src_st,
                and_(
                    src_st.id == src_ts.station_id,
                    src_st.station_code == source_station_code,
                ),
            )
            .join(dst_ts, dst_ts.train_id == Trains.id)
            .join(
                dst_st,
                and_(
                    dst_st.id == dst_ts.station_id,
                    dst_st.station_code == destination_station_code,
                ),
            )
            .where(Trains.train_number == train_number)
            .limit(1)
        )
        km = (await db.execute(stmt)).scalar_one_or_none()
        if km is None:
            return None
        return abs(int(km))

    async def _class_in_bucket(
        self, db: AsyncSession, uid: uuid.UUID, bucket: DistanceBucket | None
    ) -> tuple[str, float, int]:
        """Mode train_class within the journey's distance bucket. Falls back to the
        overall mode when the bucket is unknown or the user has no trips in it."""
        if bucket is not None:
            lo, hi = bucket_bounds(bucket)
            rows = await self._class_counts(db, uid, lo, hi)
            if rows:
                return self._top_with_confidence(rows)
        rows = await self._class_counts(db, uid, None, None)
        if rows:
            return self._top_with_confidence(rows)
        return (DEFAULT_TRAIN_CLASS, DEFAULT_CONFIDENCE, 0)

    async def _class_counts(
        self, db: AsyncSession, uid: uuid.UUID, lo: int | None, hi: int | None
    ) -> list[tuple[str, int]]:
        src_ts = aliased(TrainStations)
        dst_ts = aliased(TrainStations)
        dist_expr = dst_ts.distance_km - src_ts.distance_km
        legs = (
            select(Bookings.train_class.label("cls"), func.abs(dist_expr).label("km"))
            .join(
                src_ts,
                and_(
                    src_ts.train_id == Bookings.train_id,
                    src_ts.station_id == Bookings.source_station_id,
                ),
            )
            .join(
                dst_ts,
                and_(
                    dst_ts.train_id == Bookings.train_id,
                    dst_ts.station_id == Bookings.destination_station_id,
                ),
            )
            .where(Bookings.user_id == uid)
            .subquery()
        )
        stmt = select(legs.c.cls, func.count().label("cnt"))
        if lo is not None and hi is not None:
            stmt = stmt.where(and_(legs.c.km >= lo, legs.c.km < hi))
        stmt = stmt.group_by(legs.c.cls).order_by(func.count().desc())
        return [(r.cls, int(r.cnt)) for r in (await db.execute(stmt)).all()]

    async def _mode_quota(
        self, db: AsyncSession, uid: uuid.UUID, booking_count: int
    ) -> tuple[str, float]:
        stmt = (
            select(Bookings.quota, func.count().label("cnt"))
            .where(Bookings.user_id == uid)
            .group_by(Bookings.quota)
            .order_by(func.count().desc())
        )
        rows = [(r.quota, int(r.cnt)) for r in (await db.execute(stmt)).all()]
        if not rows:
            return (DEFAULT_QUOTA, DEFAULT_CONFIDENCE)
        value, top = rows[0]
        total = sum(c for _, c in rows) or 1
        return (value, round(top / total, CONFIDENCE_DECIMALS))

    async def _enriched_passengers(
        self, db: AsyncSession, uid: uuid.UUID, booking_count: int
    ) -> list[dict]:
        """Most-booked passengers enriched with profile (name/age/gender) and the
        history-mode berth — so the frontend needs no follow-up call."""
        freq = await self._frequent_passengers(db, uid, booking_count)
        if not freq:
            return []
        ids = [uuid.UUID(p["passenger_id"]) for p in freq]
        profiles = await self._passenger_profiles(db, ids)
        berths = await self._berth_by_passenger(
            db, uid, [p["passenger_id"] for p in freq]
        )

        enriched: list[dict] = []
        for p in freq:
            pid = p["passenger_id"]
            prof = profiles.get(pid)
            if not prof:
                continue
            berth = berths.get(
                pid,
                {"value": prof["berth_preference"], "confidence": DEFAULT_CONFIDENCE},
            )
            enriched.append(
                {
                    "passenger_id": pid,
                    "full_name": prof["full_name"],
                    "age": prof["age"],
                    "gender": prof["gender"],
                    "berth": berth,
                    "confidence": p["confidence"],
                }
            )
        return enriched

    async def _frequent_passengers(
        self, db: AsyncSession, uid: uuid.UUID, booking_count: int
    ) -> list[dict]:
        stmt = (
            select(
                BookingPassengers.passenger_id,
                func.count(distinct(Bookings.id)).label("uses"),
            )
            .join(Bookings, Bookings.id == BookingPassengers.booking_id)
            .where(Bookings.user_id == uid)
            .group_by(BookingPassengers.passenger_id)
            .order_by(func.count(distinct(Bookings.id)).desc())
            .limit(PASSENGER_SUGGESTION_LIMIT)
        )
        rows = (await db.execute(stmt)).all()
        denom = booking_count or 1
        return [
            {
                "passenger_id": str(r.passenger_id),
                "confidence": round(min(int(r.uses) / denom, 1.0), CONFIDENCE_DECIMALS),
            }
            for r in rows
        ]

    async def _passenger_profiles(
        self, db: AsyncSession, ids: list[uuid.UUID]
    ) -> dict[str, dict]:
        stmt = select(
            Passengers.id,
            Passengers.full_name,
            Passengers.age,
            Passengers.gender,
            Passengers.berth_preference,
        ).where(Passengers.id.in_(ids))
        return {
            str(r.id): {
                "full_name": r.full_name,
                "age": r.age,
                "gender": r.gender,
                "berth_preference": r.berth_preference,
            }
            for r in (await db.execute(stmt)).all()
        }

    async def _berth_by_passenger(
        self, db: AsyncSession, uid: uuid.UUID, passenger_ids: list[str]
    ) -> dict[str, dict]:
        if not passenger_ids:
            return {}
        ids = [uuid.UUID(pid) for pid in passenger_ids]
        stmt = (
            select(
                BookingPassengers.passenger_id,
                BookingPassengers.berth_preference,
                func.count().label("cnt"),
            )
            .join(Bookings, Bookings.id == BookingPassengers.booking_id)
            .where(
                and_(
                    Bookings.user_id == uid,
                    BookingPassengers.passenger_id.in_(ids),
                )
            )
            .group_by(
                BookingPassengers.passenger_id, BookingPassengers.berth_preference
            )
        )
        rows = (await db.execute(stmt)).all()

        # aggregate per passenger: total count + best (mode) berth
        totals: dict[str, int] = {}
        best: dict[str, tuple[str, int]] = {}
        for r in rows:
            pid = str(r.passenger_id)
            totals[pid] = totals.get(pid, 0) + int(r.cnt)
            if pid not in best or int(r.cnt) > best[pid][1]:
                best[pid] = (r.berth_preference, int(r.cnt))

        result: dict[str, dict] = {}
        for pid, (berth, cnt) in best.items():
            total = totals.get(pid, 0) or 1
            result[pid] = {
                "value": berth,
                "confidence": round(cnt / total, CONFIDENCE_DECIMALS),
            }
        return result

    async def _primary_passenger(self, db: AsyncSession, uid: uuid.UUID) -> dict | None:
        stmt = (
            select(
                Passengers.id,
                Passengers.full_name,
                Passengers.age,
                Passengers.gender,
            )
            .where(and_(Passengers.user_id == uid, Passengers.is_primary.is_(True)))
            .limit(1)
        )
        row = (await db.execute(stmt)).first()
        if row is None:
            return None
        return {
            "id": row.id,
            "full_name": row.full_name,
            "age": row.age,
            "gender": row.gender,
        }

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _top_with_confidence(
        self, rows: list[tuple[str, int]]
    ) -> tuple[str, float, int]:
        value, top = rows[0]
        total = sum(c for _, c in rows) or 1
        return (value, round(top / total, CONFIDENCE_DECIMALS), total)

    async def _log_suggestion(
        self,
        db: AsyncSession,
        uid: uuid.UUID,
        train_number: str,
        source_station_code: str,
        destination_station_code: str,
        result: dict,
    ) -> None:
        """Persist what was suggested. Later linked to what the user actually
        chose (CLASS_SELECTED / BOOKING_COMPLETED) to build Level-2 training data."""
        log = UserBehaviorLogs(
            user_id=str(uid),
            action_type=UserActionType.AUTOFILL_REQUESTED.value,
            action_metadata={
                "request": {
                    "train_number": train_number,
                    "source_station_code": source_station_code,
                    "destination_station_code": destination_station_code,
                },
                "suggestion": result,
            },
        )
        db.add(log)
        await db.flush()
