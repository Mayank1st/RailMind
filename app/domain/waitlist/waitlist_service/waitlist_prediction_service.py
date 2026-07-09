from __future__ import annotations

import logging
from datetime import date

from fastapi import status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.advisor_flags import AdvisorState
from app.core.exceptions import RailMindException
from app.db.models.booking import Bookings, BookingPassengers
from app.db.models.waiting_list import WaitlistEntries
from app.domain.booking.constants.booking import BookingStatus
from app.domain.waitlist.constants.waitlist_predictor import (
    BUCKET_ACTION,
    ERROR_CODE_PREDICTION,
    PredictionBucket,
    PredictionSource,
    PredictionStatus,
)
from app.domain.waitlist.waitlist_service.waitlist_alternatives_service import (
    WaitlistAlternativesService,
)
from app.domain.waitlist.waitlist_service.waitlist_model_service import (
    WaitlistModelService,
)
from app.domain.waitlist.waitlist_service.waitlist_reason_service import (
    WaitlistReasonService,
)
from app.domain.waitlist.waitlist_service.waitlist_rules_service import (
    WaitlistRulesService,
)

logger = logging.getLogger(__name__)


class WaitlistPredictionService:
    """Orchestrates the waitlist confirmation prediction (planning doc §4/§5).

    Fetches the user's own WL booking, runs the pre-checks (not-waitlisted /
    TQWL overlay), then routes to the predictor. Phase-1 routes to L1 (rules);
    L2 (model) and L3 (Gemini reason) slot in here later. Every risky step is
    guarded — a failed prediction degrades to a safe, pessimistic default rather
    than blocking the endpoint (graceful degradation).
    """

    def __init__(self) -> None:
        self._rules = WaitlistRulesService()
        self._model = WaitlistModelService()
        self._reason = WaitlistReasonService()
        self._alternatives = WaitlistAlternativesService()

    async def predict(
        self,
        *,
        pnr: str,
        db: AsyncSession,
        current_user_id: str,
        explain: bool = False,
        advisor_state: str = AdvisorState.ON.value,
    ) -> dict:
        booking = await self._fetch_owned_booking(db, pnr, current_user_id)

        # Pre-check: already CNF/RAC -> no prediction needed (planning doc §4).
        if booking.booking_status != BookingStatus.WAITLISTED.value:
            return self._not_waitlisted_result(booking.booking_status)

        wl_entry = self._first_wl_entry(booking)
        if wl_entry is None:
            # Status says WL but no WL entry attached — treat as nothing to predict.
            return self._not_waitlisted_result(booking.booking_status)

        days_to_journey = max((booking.journey_date - date.today()).days, 0)

        # Admin toggle: OFF -> skip prediction entirely (disabled response).
        if advisor_state == AdvisorState.OFF.value:
            return self._degraded_result(wl_entry, days_to_journey)

        try:
            if (
                advisor_state != AdvisorState.FORCE_RULES.value
                and self._model.is_available()
            ):
                result = await self._model.predict(
                    db,
                    wl_type=wl_entry.wl_type,
                    current_position=wl_entry.current_position,
                    booking_position=wl_entry.booking_position,
                    days_to_journey=days_to_journey,
                    train_id=booking.train_id,
                    train_class=booking.train_class,
                    quota=booking.quota,
                    journey_date=booking.journey_date,
                )
            else:
                result = await self._rules.predict(
                    db,
                    wl_type=wl_entry.wl_type,
                    current_position=wl_entry.current_position,
                    booking_position=wl_entry.booking_position,
                    days_to_journey=days_to_journey,
                    train_id=booking.train_id,
                    train_class=booking.train_class,
                )
        except Exception:
            logger.exception(
                "%s waitlist prediction failed for pnr=%s",
                ERROR_CODE_PREDICTION,
                pnr,
            )
            result = self._degraded_result(wl_entry, days_to_journey)

        # Alternatives — only when the prediction flags it (LOW bucket). Best-effort
        # reuse of Phase-1 search; never blocks the prediction (planning doc §3).
        if result.get("suggest_alternatives"):
            result["alternatives"] = await self._alternatives.find(
                db,
                from_code=booking.source_station.station_code,
                to_code=booking.destination_station.station_code,
                journey_date=booking.journey_date,
                train_class=booking.train_class,
                quota=booking.quota,
                exclude_train_number=booking.train.train_number,
            )

        # L3 — layer the Gemini reason on top of a real prediction (best-effort;
        # falls back to the templated reason internally). Skipped on the degraded
        # path (no probability) so we never dress up a failure as confident advice.
        if explain and result.get("confirmation_probability") is not None:
            result["reason"] = await self._reason.generate_reason(result)

        return result

    # ── DB read (ownership-checked) ───────────────────────────────────────────

    async def _fetch_owned_booking(
        self, db: AsyncSession, pnr: str, current_user_id: str
    ) -> Bookings:
        stmt = (
            select(Bookings)
            .options(
                selectinload(Bookings.booking_passengers).selectinload(
                    BookingPassengers.waitlist_entry
                ),
                selectinload(Bookings.train),
                selectinload(Bookings.source_station),
                selectinload(Bookings.destination_station),
            )
            .where(
                Bookings.pnr_number == pnr,
                Bookings.user_id == current_user_id,
            )
        )
        booking = (await db.execute(stmt)).scalar_one_or_none()
        if booking is None:
            raise RailMindException(
                code="RM-PNR-001",
                message="PNR not found",
                status_code=status.HTTP_404_NOT_FOUND,
            )
        return booking

    def _first_wl_entry(self, booking: Bookings) -> WaitlistEntries | None:
        return next(
            (
                bp.waitlist_entry
                for bp in booking.booking_passengers
                if bp.waitlist_entry is not None
            ),
            None,
        )

    # ── Result builders for the non-prediction paths ──────────────────────────

    def _not_waitlisted_result(self, booking_status: str) -> dict:
        return {
            "status": PredictionStatus.NOT_WAITLISTED.value,
            "booking_status": booking_status,
            "confirmation_probability": None,
            "bucket": None,
            "action": None,
            "reason": "This booking is not on the waitlist — no prediction needed.",
            "signals": {
                "wl_type": None,
                "current_position": None,
                "booking_position": None,
                "days_to_journey": None,
                "route_cancel_rate": None,
            },
            "suggest_alternatives": False,
            "alternatives": [],
            "source": PredictionSource.RULES.value,
        }

    def _degraded_result(self, wl_entry: WaitlistEntries, days_to_journey: int) -> dict:
        """Computation failed — degrade to a safe, pessimistic LOW (under-promise
        confirmation; planning doc §6.4) while still echoing the known signals."""
        return {
            "status": PredictionStatus.WAITLISTED.value,
            "confirmation_probability": None,
            "bucket": PredictionBucket.LOW.value,
            "action": BUCKET_ACTION[PredictionBucket.LOW],
            "reason": (
                "We couldn't generate a prediction right now — to be safe, consider "
                "making a backup plan."
            ),
            "signals": {
                "wl_type": wl_entry.wl_type,
                "current_position": wl_entry.current_position,
                "booking_position": wl_entry.booking_position,
                "days_to_journey": days_to_journey,
                "route_cancel_rate": None,
            },
            "suggest_alternatives": True,
            "alternatives": [],
            "source": PredictionSource.RULES.value,
        }
