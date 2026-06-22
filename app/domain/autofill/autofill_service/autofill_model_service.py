from __future__ import annotations

import uuid
from collections import Counter
from datetime import date

from sqlalchemy import and_, func, select, text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from app.ai.pipelines.autofill_class import AutofillClassModel
from app.ai.pipelines.autofill_features import (
    DISTANCE_WINDOW_KM,
    HIST_NONE,
    RECENCY_WINDOW,
    bucket_value_for_km,
    departure_hour,
    hour_is_night,
    is_festival_month,
)
from app.config import settings
from app.db.base import DB_SCHEMA
from app.db.models.booking import Bookings
from app.db.models.train import Trains, TrainStations
from app.domain.autofill.autofill_service.autofill_rules_service import (
    AutofillRulesService,
)
from app.domain.autofill.constants.autofill import AutofillSource

_PASSENGER_STATS_SQL = text(
    f"""
    WITH per_booking AS (
        SELECT bp.booking_id,
               count(*) AS cnt,
               bool_or(p.age >= 60) AS snr,
               bool_or(p.age < 12) AS chd
        FROM {DB_SCHEMA}.booking_passengers bp
        JOIN {DB_SCHEMA}.passengers p ON p.id = bp.passenger_id
        JOIN {DB_SCHEMA}.bookings b ON b.id = bp.booking_id
        WHERE b.user_id = :uid
        GROUP BY bp.booking_id
    )
    SELECT mode() WITHIN GROUP (ORDER BY cnt) AS typical,
           bool_or(snr) AS ever_senior,
           bool_or(chd) AS ever_child
    FROM per_booking
    """
)


class AutofillModelService:
    """Level-2 Smart Form Autofill — global XGBoost model predicts train_class.

    Reuses AutofillRulesService for the quota / passenger / distance scaffold, then
    overrides train_class with the model prediction (confidence = max softprob).
    Response shape stays identical to Level 1; only `source` (MODEL) and
    `model_version` are added.
    """

    def __init__(self) -> None:
        self._rules = AutofillRulesService()

    @staticmethod
    def is_available() -> bool:
        return AutofillClassModel.is_available()

    async def suggest_autofill(
        self,
        db: AsyncSession,
        user_id: str,
        train_number: str,
        source_station_code: str,
        destination_station_code: str,
        journey_date: date | None = None,
    ) -> dict:
        uid = uuid.UUID(user_id)
        scaffold = await self._rules.build_suggestion(
            db, user_id, train_number, source_station_code, destination_station_code
        )
        raw = await self._build_features(db, uid, train_number, scaffold, journey_date)
        prediction = AutofillClassModel.predict(raw)
        confidence = prediction["confidence"]

        scaffold["train_class"] = {
            "value": prediction["value"],
            "confidence": confidence,
        }
        scaffold["source"] = AutofillSource.MODEL.value
        scaffold["model_version"] = prediction["model_version"]
        scaffold["based_on_bookings"] = scaffold["booking_count"]
        scaffold["auto_fill"] = confidence >= settings.AI_CONFIDENCE_THRESHOLD

        await self._rules._log_suggestion(
            db,
            uid,
            train_number,
            source_station_code,
            destination_station_code,
            scaffold,
        )
        return scaffold

    # ── Feature assembly (leakage-free) ───────────────────────────────────────

    async def _build_features(
        self,
        db: AsyncSession,
        uid: uuid.UUID,
        train_number: str,
        scaffold: dict,
        journey_date: date | None,
    ) -> dict:
        jd = journey_date or date.today()
        distance_km = scaffold.get("journey_distance_km") or 0
        bucket = scaffold.get("distance_bucket") or bucket_value_for_km(distance_km)

        dep_hour = await self._source_departure_hour(db, train_number)
        typical_count, ever_senior, ever_child = await self._passenger_stats(db, uid)
        top_class, bucket_class, recent_class, distance_class = (
            await self._history_classes(db, uid, bucket, distance_km)
        )

        return {
            "distance_km": distance_km,
            "distance_bucket": bucket,
            "is_night_train": hour_is_night(dep_hour),
            "passenger_count": typical_count,
            "has_senior": ever_senior,
            "has_child": ever_child,
            "is_weekend": jd.weekday() >= 5,
            "month": jd.month,
            "is_festival_season": is_festival_month(jd.month),
            "quota": scaffold["quota"]["value"],
            "user_hist_top_class": top_class,
            "user_hist_class_for_bucket": bucket_class,
            "user_hist_recent_class": recent_class,
            "user_hist_class_for_distance": distance_class,
        }

    async def _source_departure_hour(self, db: AsyncSession, train_number: str) -> int:
        stmt = (
            select(TrainStations.departure_time)
            .select_from(Trains)
            .join(
                TrainStations,
                and_(
                    TrainStations.train_id == Trains.id,
                    TrainStations.is_source.is_(True),
                ),
            )
            .where(Trains.train_number == train_number)
            .limit(1)
        )
        return departure_hour((await db.execute(stmt)).scalar_one_or_none())

    async def _passenger_stats(
        self, db: AsyncSession, uid: uuid.UUID
    ) -> tuple[int, bool, bool]:
        row = (await db.execute(_PASSENGER_STATS_SQL, {"uid": str(uid)})).first()
        if not row or row.typical is None:
            return (1, False, False)
        return (int(row.typical), bool(row.ever_senior), bool(row.ever_child))

    async def _history_classes(
        self,
        db: AsyncSession,
        uid: uuid.UUID,
        journey_bucket: str,
        journey_km: int,
    ) -> tuple[str, str, str, str]:
        src_ts = aliased(TrainStations)
        dst_ts = aliased(TrainStations)
        stmt = (
            select(
                Bookings.train_class.label("cls"),
                func.abs(dst_ts.distance_km - src_ts.distance_km).label("km"),
            )
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
            .order_by(Bookings.booked_at)
        )
        rows = (await db.execute(stmt)).all()
        if not rows:
            return (HIST_NONE, HIST_NONE, HIST_NONE, HIST_NONE)

        classes = [r.cls for r in rows]
        overall = Counter(classes).most_common(1)[0][0]
        bucket_classes = [
            r.cls for r in rows if bucket_value_for_km(int(r.km)) == journey_bucket
        ]
        bucket_top = (
            Counter(bucket_classes).most_common(1)[0][0]
            if bucket_classes
            else HIST_NONE
        )
        recent = Counter(classes[-RECENCY_WINDOW:]).most_common(1)[0][0]
        nearby_classes = [
            r.cls for r in rows if abs(int(r.km) - journey_km) <= DISTANCE_WINDOW_KM
        ]
        nearby = (
            Counter(nearby_classes).most_common(1)[0][0]
            if nearby_classes
            else HIST_NONE
        )
        return (overall, bucket_top, recent, nearby)
