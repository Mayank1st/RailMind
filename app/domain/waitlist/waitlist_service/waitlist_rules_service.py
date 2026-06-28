from __future__ import annotations

import math
from datetime import date
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.booking import Bookings
from app.domain.booking.constants.booking import (
    CANCELLED_BOOKING_STATUSES,
    WaitlistType,
)
from app.domain.waitlist.constants.waitlist_predictor import (
    ALT_THRESHOLD,
    BUCKET_ACTION,
    BUCKET_HIGH_MIN,
    BUCKET_LOW_MAX,
    DAYS_MID_MIN,
    DAYS_NEAR,
    DAYS_PEAK_MIN,
    DAYS_TOO_EARLY,
    DEFAULT_ROUTE_CANCEL_RATE,
    MAX_PROB,
    MIN_HISTORY_FOR_CANCEL_RATE,
    MIN_PROB,
    MULT_DAYS_IMMINENT,
    MULT_DAYS_MID,
    MULT_DAYS_NEAR,
    MULT_DAYS_PEAK,
    MULT_DAYS_TOO_EARLY,
    PROB_DECIMALS,
    RATIO_CENTER,
    RATIO_LOGISTIC_K,
    REFERENCE_WL_DEPTH,
    REFERENCE_WL_DEPTH_DEFAULT,
    TQWL_MAX_PROB,
    WL_TYPE_MULTIPLIER,
    WL_TYPE_MULTIPLIER_DEFAULT,
    PredictionBucket,
    PredictionSource,
    PredictionStatus,
)


class WaitlistRulesService:
    """Level-1 (rules) waitlist confirmation predictor.

    Estimates P(WL → CNF) from the as-of-now WL position against how many seats
    the route/class historically sheds (route_cancel_rate × confirmed seats),
    nudged by the WL type (GNWL > RLWL > PQWL > TQWL) and the lead time left.
    Pure read path — never writes. Cold-start + fallback friendly: with no live
    capacity it falls back to the WL-type prior, and TQWL is structurally capped
    (it never reaches RAC). Output is safe-biased toward pessimism — when unsure,
    don't over-promise a confirmation (planning doc §6.4).
    """

    async def predict(
        self,
        db: AsyncSession,
        *,
        wl_type: str,
        current_position: int,
        booking_position: int,
        days_to_journey: int,
        train_id: UUID,
        train_class: str,
    ) -> dict:
        route_cancel_rate = await self._route_cancel_rate(db, train_id, train_class)
        rate_used = (
            route_cancel_rate
            if route_cancel_rate is not None
            else DEFAULT_ROUTE_CANCEL_RATE
        )
        probability = self._estimate_probability(
            wl_type=wl_type,
            train_class=train_class,
            current_position=current_position,
            days_to_journey=days_to_journey,
            route_cancel_rate=rate_used,
        )
        return self.build_result(
            probability=probability,
            wl_type=wl_type,
            current_position=current_position,
            booking_position=booking_position,
            days_to_journey=days_to_journey,
            route_cancel_rate=rate_used,
        )

    # ── Probability estimate ──────────────────────────────────────────────────

    def _estimate_probability(
        self,
        *,
        wl_type: str,
        train_class: str,
        current_position: int,
        days_to_journey: int,
        route_cancel_rate: float,
    ) -> float:
        # Ratio core (planning doc §5/§6.2): compare the position against how many
        # seats the route/class realistically sheds before the journey.
        reference_depth = REFERENCE_WL_DEPTH.get(
            train_class, REFERENCE_WL_DEPTH_DEFAULT
        )
        clearable_depth = route_cancel_rate * reference_depth
        ratio = clearable_depth / max(current_position, 1)
        probability = self._ratio_to_prob(ratio)

        probability *= WL_TYPE_MULTIPLIER.get(wl_type, WL_TYPE_MULTIPLIER_DEFAULT)
        probability *= self._days_multiplier(days_to_journey)

        # TQWL never reaches RAC — hard structural cap (planning doc §4 pre-check).
        if wl_type == WaitlistType.TQWL.value:
            probability = min(probability, TQWL_MAX_PROB)

        return round(self._clamp(probability, MIN_PROB, MAX_PROB), PROB_DECIMALS)

    def _ratio_to_prob(self, ratio: float) -> float:
        """Logistic centred on ratio = 1.0 (just enough cancellations to clear the
        position): ratio >> 1 -> high, ratio << 1 -> low."""
        return 1.0 / (1.0 + math.exp(-RATIO_LOGISTIC_K * (ratio - RATIO_CENTER)))

    def _days_multiplier(self, days_to_journey: int) -> float:
        if days_to_journey > DAYS_TOO_EARLY:
            return MULT_DAYS_TOO_EARLY
        if days_to_journey >= DAYS_MID_MIN:
            return MULT_DAYS_MID
        if days_to_journey >= DAYS_PEAK_MIN:
            return MULT_DAYS_PEAK
        if days_to_journey >= DAYS_NEAR:
            return MULT_DAYS_NEAR
        return MULT_DAYS_IMMINENT

    def _clamp(self, value: float, low: float, high: float) -> float:
        return max(low, min(high, value))

    # ── Result assembly (shape shared with the L2 model path) ─────────────────

    def build_result(
        self,
        *,
        probability: float,
        wl_type: str,
        current_position: int,
        booking_position: int,
        days_to_journey: int,
        route_cancel_rate: float,
        source: str = PredictionSource.RULES.value,
    ) -> dict:
        bucket = self._bucket(probability)
        return {
            "status": PredictionStatus.WAITLISTED.value,
            "confirmation_probability": probability,
            "bucket": bucket.value,
            "action": BUCKET_ACTION[bucket],
            "reason": self._build_reason(
                bucket=bucket,
                wl_type=wl_type,
                current_position=current_position,
                days_to_journey=days_to_journey,
                route_cancel_rate=route_cancel_rate,
            ),
            "signals": {
                "wl_type": wl_type,
                "current_position": current_position,
                "booking_position": booking_position,
                "days_to_journey": days_to_journey,
                "route_cancel_rate": round(route_cancel_rate, PROB_DECIMALS),
            },
            "suggest_alternatives": probability < ALT_THRESHOLD,
            "alternatives": [],
            "source": source,
        }

    def _bucket(self, probability: float) -> PredictionBucket:
        if probability > BUCKET_HIGH_MIN:
            return PredictionBucket.HIGH
        if probability < BUCKET_LOW_MAX:
            return PredictionBucket.LOW
        return PredictionBucket.MEDIUM

    def _build_reason(
        self,
        *,
        bucket: PredictionBucket,
        wl_type: str,
        current_position: int,
        days_to_journey: int,
        route_cancel_rate: float,
    ) -> str:
        """Deterministic templated reason (Level-3 Gemini will later rephrase it
        into a richer line). Numbers are computed here; Gemini never invents any."""
        pct = round(route_cancel_rate * 100)
        if wl_type == WaitlistType.TQWL.value:
            return (
                "This is a TQWL (Tatkal waitlist) — Tatkal waitlists never move to "
                "RAC, so the chance of confirmation is structurally very low."
            )
        if bucket is PredictionBucket.HIGH:
            return (
                f"Around {pct}% of bookings on this route/class usually cancel and "
                f"you are at position {current_position} — a strong chance of "
                f"confirmation."
            )
        if bucket is PredictionBucket.MEDIUM:
            return (
                f"About {pct}% of bookings on this route cancel, you are at position "
                f"{current_position}, and there are still {days_to_journey} days to "
                f"the journey — there is time to move up, but no guarantee."
            )
        return (
            f"Position {current_position} is quite far back and only about {pct}% of "
            f"bookings on this route cancel — confirmation looks unlikely; consider "
            f"a backup."
        )

    # ── DB reads ──────────────────────────────────────────────────────────────

    async def _route_cancel_rate(
        self, db: AsyncSession, train_id: UUID, train_class: str
    ) -> float | None:
        """Historical fraction of bookings on this train+class that ended cancelled.
        None when there isn't enough past data to be meaningful (cold-start)."""
        cancelled = func.count().filter(
            Bookings.booking_status.in_(CANCELLED_BOOKING_STATUSES)
        )
        stmt = select(cancelled, func.count()).where(
            Bookings.train_id == train_id,
            Bookings.train_class == train_class,
            Bookings.journey_date < date.today(),
        )
        cancelled_count, total = (await db.execute(stmt)).one()
        if total is None or total < MIN_HISTORY_FOR_CANCEL_RATE:
            return None
        return cancelled_count / total
