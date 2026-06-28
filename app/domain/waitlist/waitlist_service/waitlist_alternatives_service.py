from __future__ import annotations

import logging
from datetime import date

from sqlalchemy import select, tuple_
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.train import SeatInventories, Trains
from app.domain.booking.constants.booking import BookingAvailabilityStatus
from app.domain.train.dto.train_request_dto import SearchTrainDTO
from app.domain.train.train_service.train_service import TrainService
from app.domain.waitlist.constants.waitlist_predictor import (
    ALT_FLEX_DAYS,
    ALT_LIMIT,
    ALT_SEARCH_SIZE,
    ERROR_CODE_PREDICTION,
)

logger = logging.getLogger(__name__)

_AVAIL_RANK = {
    BookingAvailabilityStatus.AVAILABLE.value: 0,
    BookingAvailabilityStatus.RAC.value: 1,
    BookingAvailabilityStatus.WL.value: 2,
}
_UNKNOWN_RANK = 3


class WaitlistAlternativesService:
    """Best-effort alternative-train suggestions for a low-chance waitlist.

    Finding alternatives is search's job, not the predictor's (planning doc §3) —
    so this reuses Phase-1's `search_trains` (which already expands ±flex_days and
    sorts requested-date-first), then enriches each candidate with live availability
    from seat_inventories (same AVAILABLE/RAC/WL/REGRET semantics as Phase-1's
    seat-availability). Dead-ends (REGRET) are dropped and the rest are ranked
    best-availability-first, so every suggestion is actually actionable. Runs only
    on the LOW bucket; any failure returns [] (never blocks the prediction).
    """

    def __init__(self) -> None:
        self._train = TrainService()

    async def find(
        self,
        db: AsyncSession,
        *,
        from_code: str,
        to_code: str,
        journey_date: date,
        train_class: str,
        quota: str,
        exclude_train_number: str,
        limit: int = ALT_LIMIT,
    ) -> list[dict]:
        try:
            payload = SearchTrainDTO(
                fromStationCode=from_code,
                toStationCode=to_code,
                journey_date=journey_date,
                train_class=train_class,  # coerced to TrainClass
                quota=quota,  # coerced to Quota
                flexible_dates=True,
                flex_days=ALT_FLEX_DAYS,
                size=ALT_SEARCH_SIZE,
            )
            result = await self._train.search_trains(payload, db)
        except Exception:
            logger.warning(
                "%s alternatives search failed for %s->%s on %s",
                ERROR_CODE_PREDICTION,
                from_code,
                to_code,
                journey_date,
            )
            return []

        # Candidate trains (drop the user's own stuck train + non-running ones).
        candidates = [
            t
            for t in result.get("items", [])
            if t.get("train_number") != exclude_train_number
            and t.get("runs_today") is not False
        ]
        if not candidates:
            return []

        # Live availability per candidate (best-effort; {} on failure -> all unknown).
        avail = await self._availability_map(db, candidates, train_class, quota)

        ranked: list[tuple[int, int, dict]] = []
        for idx, t in enumerate(candidates):
            status, seats = avail.get(
                (t.get("train_number"), t.get("journey_date")), (None, None)
            )
            if status == BookingAvailabilityStatus.REGRET.value:
                continue  # dead-end — never suggest a fully-regret train
            ranked.append(
                (
                    _AVAIL_RANK.get(status, _UNKNOWN_RANK),
                    idx,
                    self._to_alternative(t, status, seats),
                )
            )

        # Best availability first; ties keep Phase-1's requested-date-first order.
        ranked.sort(key=lambda r: (r[0], r[1]))
        return [alt for _, _, alt in ranked[:limit]]

    async def _availability_map(
        self, db: AsyncSession, candidates: list[dict], train_class: str, quota: str
    ) -> dict[tuple[str, str], tuple[str, int]]:
        """{(train_number, journey_date_iso): (availability, available_seats)} via one
        batched seat_inventories read. Empty on any failure (callers treat as unknown).
        """
        try:
            numbers = {t["train_number"] for t in candidates}
            num_rows = (
                await db.execute(
                    select(Trains.id, Trains.train_number).where(
                        Trains.train_number.in_(list(numbers))
                    )
                )
            ).all()
            num_to_id = {r.train_number: r.id for r in num_rows}
            id_to_num = {r.id: r.train_number for r in num_rows}

            keys = set()
            for t in candidates:
                tid = num_to_id.get(t["train_number"])
                if tid is None:
                    continue
                keys.add(
                    (tid, date.fromisoformat(t["journey_date"]), train_class, quota)
                )
            if not keys:
                return {}

            key_cols = tuple_(
                SeatInventories.train_id,
                SeatInventories.journey_date,
                SeatInventories.train_class,
                SeatInventories.quota,
            )
            stmt = select(
                SeatInventories.train_id,
                SeatInventories.journey_date,
                SeatInventories.available_confirmed_seats,
                SeatInventories.available_rac_slots,
                SeatInventories.wl_count,
                SeatInventories.wl_max,
            ).where(key_cols.in_(list(keys)))

            out: dict[tuple[str, str], tuple[str, int]] = {}
            for r in (await db.execute(stmt)).all():
                num = id_to_num.get(r.train_id)
                if num is None:
                    continue
                out[(num, r.journey_date.isoformat())] = (
                    self._availability(
                        r.available_confirmed_seats,
                        r.available_rac_slots,
                        r.wl_count,
                        r.wl_max,
                    ),
                    int(r.available_confirmed_seats),
                )
            return out
        except Exception:
            logger.warning(
                "%s alternatives availability lookup failed", ERROR_CODE_PREDICTION
            )
            return {}

    @staticmethod
    def _availability(cnf: int, rac: int, wl: int, wl_max: int) -> str:
        """Same semantics as SeatInventories.booking_availability / Phase-1's
        seat-availability."""
        if cnf > 0:
            return BookingAvailabilityStatus.AVAILABLE.value
        if rac > 0:
            return BookingAvailabilityStatus.RAC.value
        if wl < wl_max:
            return BookingAvailabilityStatus.WL.value
        return BookingAvailabilityStatus.REGRET.value

    @staticmethod
    def _to_alternative(
        t: dict, availability: str | None, available_seats: int | None
    ) -> dict:
        return {
            "train_number": t.get("train_number"),
            "train_name": t.get("train_name"),
            "train_type": t.get("train_type"),
            "journey_date": t.get("journey_date"),
            "date_offset_days": t.get("date_offset_days"),
            "departs": t.get("departs"),
            "arrives": t.get("arrives"),
            "duration_minutes": t.get("duration_minutes"),
            "availability": availability,  # AVAILABLE | RAC | WL | null (unknown)
            "available_seats": available_seats,  # confirmed seats left; null if unknown
        }
