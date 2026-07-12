from __future__ import annotations

import logging
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from fastapi import status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.advisor_flags import AdvisorState
from app.core.exceptions import RailMindException
from app.core.refund_calculator import (
    CLERKAGE_CHARGE,
    RefundCalculator,
    TATKAL_QUOTAS,
)
from app.db.models.booking import Bookings
from app.db.models.train import SeatInventories, TrainStations
from app.domain.booking.constants.booking import (
    CANCELLED_BOOKING_STATUSES,
    BookingStatus,
    PassengerStatus,
)
from app.domain.cancellation.cancellation_service.cancellation_reason_service import (
    CancellationReasonService,
)
from app.domain.cancellation.constants.cancellation_advisor import (
    AMOUNT_DECIMALS,
    ERROR_CODE_ADVISOR,
    FALLBACK_DEPARTURE_HOUR,
    HOURS_DECIMALS,
    LADDER_WINDOWS,
    RECOMMENDATION_ACTION,
    WL_BUCKET_RECOMMENDATION,
    WL_DEGRADED_RECOMMENDATION,
    AdviceRecommendation,
    AdviceSource,
    AdviceStatus,
)
from app.domain.waitlist.waitlist_service.waitlist_prediction_service import (
    WaitlistPredictionService,
)

logger = logging.getLogger(__name__)

_IST = ZoneInfo("Asia/Kolkata")

# Passenger statuses that still hold inventory — the ones a cancellation refunds.
_ACTIVE_PASSENGER_STATUSES = (
    PassengerStatus.CONFIRMED.value,
    PassengerStatus.RAC.value,
    PassengerStatus.WAITLISTED.value,
)


class CancellationAdvisorService:
    """Orchestrates the cancellation advice for one booking (Phase-2 feature 07).

    Two very different halves, kept deliberately separate:
      - Refund amount — DETERMINISTIC. RefundCalculator applies the IRCTC
        deduction slabs; nothing is predicted.
      - Cancel-or-wait — ADVISORY. For a WL booking the question is "will it
        confirm?", answered by reusing the Waitlist Predictor (#03); for a CNF
        booking it is a timing call ("cancel before the refund drops").

    Every risky step degrades to a safe default — the advisor must never block
    the cancellation flow.
    """

    def __init__(self) -> None:
        self._refund_calculator = RefundCalculator()
        self._waitlist_prediction = WaitlistPredictionService()
        self._reason = CancellationReasonService()

    async def advise(
        self,
        *,
        pnr: str,
        db: AsyncSession,
        current_user_id: str,
        explain: bool = False,
        advisor_state: str = AdvisorState.ON.value,
        waitlist_advisor_state: str = AdvisorState.ON.value,
    ) -> dict:
        booking = await self._fetch_owned_booking(db, pnr, current_user_id)

        # Pre-checks: nothing to advise on a cancelled / unpaid booking.
        if booking.booking_status in CANCELLED_BOOKING_STATUSES:
            return self._terminal_result(
                AdviceStatus.ALREADY_CANCELLED,
                booking,
                reason="This booking is already cancelled — no advice needed.",
            )
        if booking.booking_status in (
            BookingStatus.INITIATED.value,
            BookingStatus.PAYMENT_PENDING.value,
        ):
            return self._terminal_result(
                AdviceStatus.NOT_APPLICABLE,
                booking,
                reason=(
                    "No payment has been captured for this booking yet, so there "
                    "is no refund at stake."
                ),
            )

        departure = await self._departure_datetime(db, booking)
        now = datetime.now(_IST)
        hours_to_departure = (departure - now).total_seconds() / 3600

        if hours_to_departure <= 0:
            return self._terminal_result(
                AdviceStatus.NOT_CANCELLABLE,
                booking,
                reason="The train has already departed — online cancellation is closed.",
                hours_to_departure=hours_to_departure,
            )

        is_chart_prepared = await self._is_chart_prepared(db, booking)
        if is_chart_prepared:
            return self._terminal_result(
                AdviceStatus.NOT_CANCELLABLE,
                booking,
                reason=(
                    "The chart has been prepared — online cancellation is closed "
                    "for this booking."
                ),
                hours_to_departure=hours_to_departure,
                is_chart_prepared=True,
            )

        active_passengers = [
            bp
            for bp in booking.booking_passengers
            if bp.passenger_status in _ACTIVE_PASSENGER_STATUSES
        ]
        refund = self._refund_summary(booking, active_passengers, hours_to_departure)
        signals = self._signals(booking, hours_to_departure, is_chart_prepared)

        # Admin toggle OFF: the refund math is deterministic and always safe to
        # show — only the AI advice is withheld.
        if advisor_state == AdvisorState.OFF.value:
            return self._base_result(booking, refund, signals) | {
                "reason": (
                    "Advice is currently unavailable — here is the refund you "
                    "would get if you cancel now."
                ),
            }

        # When the cancellation advisor itself is forced to rules, force the
        # embedded WL prediction down to rules too.
        if advisor_state == AdvisorState.FORCE_RULES.value:
            waitlist_advisor_state = AdvisorState.FORCE_RULES.value

        try:
            if booking.booking_status == BookingStatus.WAITLISTED.value:
                result = await self._wl_branch(
                    db=db,
                    booking=booking,
                    refund=refund,
                    signals=signals,
                    current_user_id=current_user_id,
                    waitlist_advisor_state=waitlist_advisor_state,
                )
            elif booking.booking_status == BookingStatus.RAC.value:
                result = self._rac_branch(booking, refund, signals)
            else:
                result = self._cnf_branch(
                    booking,
                    active_passengers,
                    refund,
                    signals,
                    hours_to_departure,
                    departure,
                )
        except Exception:
            logger.exception(
                "%s cancellation advice failed for pnr=%s", ERROR_CODE_ADVISOR, pnr
            )
            result = self._degraded_result(booking, refund, signals)

        # L3 — layer the LLM reason on top of real advice (best-effort; falls
        # back to the templated reason internally). Skipped when there is no
        # recommendation so we never dress up a failure as confident advice.
        if explain and result.get("recommendation") is not None:
            result["reason"] = await self._reason.generate_reason(result)

        return result

    # ── Branches ──────────────────────────────────────────────────────────────

    async def _wl_branch(
        self,
        *,
        db: AsyncSession,
        booking: Bookings,
        refund: dict,
        signals: dict,
        current_user_id: str,
        waitlist_advisor_state: str,
    ) -> dict:
        """WL booking → "will it confirm?" — reuse the Waitlist Predictor (#03).
        The refund itself barely depends on timing here (flat clerkage until 30
        minutes before departure), so the advice is driven by the confirmation
        probability, not the money."""
        wl = await self._waitlist_prediction.predict(
            pnr=booking.pnr_number,
            db=db,
            current_user_id=current_user_id,
            explain=False,
            advisor_state=waitlist_advisor_state,
        )

        prob = wl.get("confirmation_probability")
        bucket = wl.get("bucket")
        refund_txt = self._rupees(refund["refund_amount"])
        paid_txt = self._rupees(refund["total_paid"])

        if prob is None:
            # Degraded / disabled WL prediction — never advise CANCEL_NOW off a
            # failure; hold and let the user re-check.
            recommendation = WL_DEGRADED_RECOMMENDATION
            reason = (
                "We couldn't score your waitlist right now — hold for the moment. "
                f"Whenever you cancel (up to 30 minutes before departure), you get "
                f"{refund_txt} of {paid_txt} back, so waiting costs nothing."
            )
        else:
            recommendation = WL_BUCKET_RECOMMENDATION.get(
                bucket, WL_DEGRADED_RECOMMENDATION
            )
            pct = round(prob * 100)
            if recommendation == AdviceRecommendation.HOLD:
                reason = (
                    f"About {pct}% chance your waitlist confirms — hold on. If plans "
                    f"change, cancelling returns {refund_txt} of {paid_txt} (flat "
                    f"clerkage of Rs {CLERKAGE_CHARGE:.0f} per passenger), now or later."
                )
            elif recommendation == AdviceRecommendation.CANCEL_NOW:
                reason = (
                    f"Only about {pct}% chance of confirmation — cancelling now "
                    f"returns {refund_txt} of {paid_txt}, the same as waiting for "
                    f"auto-cancellation, and frees you to book an alternative."
                )
            else:
                reason = (
                    f"Roughly {pct}% chance of confirmation — hold and re-check. The "
                    f"refund ({refund_txt}) stays the same until 30 minutes before "
                    f"departure, so waiting costs nothing."
                )

        return self._base_result(booking, refund, signals) | {
            "recommendation": recommendation.value,
            "action": RECOMMENDATION_ACTION[recommendation],
            "reason": reason,
            "waitlist": {
                "confirmation_probability": prob,
                "bucket": bucket,
                "model_version": wl.get("model_version"),
            },
            "suggest_alternatives": bool(wl.get("suggest_alternatives")),
            "alternatives": wl.get("alternatives") or [],
            "source": wl.get("source") or AdviceSource.RULES.value,
        }

    def _rac_branch(self, booking: Bookings, refund: dict, signals: dict) -> dict:
        """RAC booking → travel is already assured (shared berth) and the
        deduction is a flat clerkage regardless of timing — nothing to time."""
        recommendation = AdviceRecommendation.HOLD
        reason = (
            "You hold an RAC ticket — you can board, and it often upgrades to a "
            "full berth at chart time. If plans change, cancelling any time up to "
            f"30 minutes before departure returns "
            f"{self._rupees(refund['refund_amount'])} of "
            f"{self._rupees(refund['total_paid'])} (flat clerkage only)."
        )
        return self._base_result(booking, refund, signals) | {
            "recommendation": recommendation.value,
            "action": RECOMMENDATION_ACTION[recommendation],
            "reason": reason,
        }

    def _cnf_branch(
        self,
        booking: Bookings,
        active_passengers: list,
        refund: dict,
        signals: dict,
        hours_to_departure: float,
        departure: datetime,
    ) -> dict:
        """CNF booking → a timing advisor: the earlier you cancel, the more you
        get back. We don't know whether the user WANTS to cancel — so the advice
        is about the deadline, not the decision."""
        ladder = self._refund_ladder(
            active_passengers, booking, hours_to_departure, departure
        )
        refund_now = refund["refund_amount"]

        if refund_now <= 0:
            recommendation = AdviceRecommendation.HOLD
            if booking.quota in TATKAL_QUOTAS:
                reason = (
                    "Confirmed Tatkal tickets are non-refundable — cancelling "
                    "gains you nothing, so hold the ticket."
                )
            else:
                reason = (
                    "The refund window has passed — cancelling now would return "
                    "Rs 0, so there is nothing to gain by cancelling."
                )
        else:
            next_step = self._next_drop_step(ladder)
            if next_step:
                recommendation = AdviceRecommendation.CANCEL_EARLY
                reason = (
                    f"If you might cancel, do it before {next_step['cancel_by']}: "
                    f"you'd get {self._rupees(refund_now)} of "
                    f"{self._rupees(refund['total_paid'])} back now; after that it "
                    f"drops to {self._rupees(next_step['refund_amount'])}."
                )
            else:
                recommendation = AdviceRecommendation.HOLD
                reason = (
                    f"Cancelling returns {self._rupees(refund_now)} of "
                    f"{self._rupees(refund['total_paid'])} — and that doesn't "
                    f"change between now and departure."
                )

        return self._base_result(booking, refund, signals) | {
            "recommendation": recommendation.value,
            "action": RECOMMENDATION_ACTION[recommendation],
            "reason": reason,
            "refund_ladder": ladder,
        }

    # ── Refund computation (deterministic — RefundCalculator) ────────────────

    @staticmethod
    def _passenger_fares(
        booking: Bookings, active_passengers: list
    ) -> list[tuple[float, str]]:
        """(fare, passenger_status) pairs the refund is computed over. Bookings
        without passenger rows (legacy/seeded data) degrade to one pseudo
        passenger carrying the whole booking fare."""
        if active_passengers:
            return [(float(bp.fare), bp.passenger_status) for bp in active_passengers]
        fallback_status = {
            BookingStatus.RAC.value: PassengerStatus.RAC.value,
            BookingStatus.WAITLISTED.value: PassengerStatus.WAITLISTED.value,
        }.get(booking.booking_status, PassengerStatus.CONFIRMED.value)
        return [(float(booking.total_fare), fallback_status)]

    def _refund_summary(
        self, booking: Bookings, active_passengers: list, hours_to_departure: float
    ) -> dict:
        per_passenger = []
        refund_total = 0.0
        for fare, passenger_status in self._passenger_fares(booking, active_passengers):
            breakdown = self._refund_calculator.calculate(
                fare=fare,
                passenger_status=passenger_status,
                train_class=booking.train_class,
                quota=booking.quota,
                hours_to_departure=hours_to_departure,
            )
            refund_total += breakdown.refund_amount
            per_passenger.append(breakdown.as_dict())

        total_paid = round(float(booking.total_fare), AMOUNT_DECIMALS)
        refund_total = round(refund_total, AMOUNT_DECIMALS)
        return {
            "total_paid": total_paid,
            "refund_amount": refund_total,
            # Includes the non-refundable IRCTC service charge — "paid minus got
            # back" is the number the user actually feels.
            "deduction_amount": round(total_paid - refund_total, AMOUNT_DECIMALS),
            "per_passenger": per_passenger,
        }

    def _refund_ladder(
        self,
        active_passengers: list,
        booking: Bookings,
        hours_to_departure: float,
        departure: datetime,
    ) -> list[dict]:
        """Refund at each remaining deduction window — the "cancel before X"
        table. Past windows are dropped; the first entry is the current one."""
        ladder: list[dict] = []
        for label, representative_hours, lower_bound_hours in LADDER_WINDOWS:
            if lower_bound_hours >= hours_to_departure:
                continue  # that window's deadline has already passed

            refund_total = 0.0
            rule = ""
            for fare, passenger_status in self._passenger_fares(
                booking, active_passengers
            ):
                breakdown = self._refund_calculator.calculate(
                    fare=fare,
                    passenger_status=passenger_status,
                    train_class=booking.train_class,
                    quota=booking.quota,
                    hours_to_departure=representative_hours,
                )
                refund_total += breakdown.refund_amount
                if passenger_status == PassengerStatus.CONFIRMED.value:
                    rule = breakdown.rule
                rule = rule or breakdown.rule

            cancel_by = (
                (departure - timedelta(hours=lower_bound_hours)).isoformat()
                if lower_bound_hours > 0
                else None
            )
            ladder.append(
                {
                    "window": label,
                    "cancel_by": cancel_by,
                    "refund_amount": round(refund_total, AMOUNT_DECIMALS),
                    "rule": rule,
                    "is_current": not ladder,  # first surviving window = current
                }
            )
        return ladder

    @staticmethod
    def _rupees(amount: float) -> str:
        return f"Rs {amount:.0f}"

    @staticmethod
    def _next_drop_step(ladder: list[dict]) -> dict | None:
        """First future window whose refund is LOWER than the current one — the
        deadline worth telling the user about."""
        if not ladder:
            return None
        current_refund = ladder[0]["refund_amount"]
        # The deadline is the end of the LAST window still paying the current
        # refund — adjacent windows can pay the same amount (25% of a small fare
        # can floor at the flat charge), so walk until the amount actually drops.
        deadline = ladder[0]["cancel_by"]
        for step in ladder[1:]:
            if step["refund_amount"] < current_refund:
                return {
                    "cancel_by": deadline,
                    "refund_amount": step["refund_amount"],
                }
            deadline = step["cancel_by"]
        return None

    # ── DB reads ──────────────────────────────────────────────────────────────

    async def _fetch_owned_booking(
        self, db: AsyncSession, pnr: str, current_user_id: str
    ) -> Bookings:
        stmt = (
            select(Bookings)
            .options(
                selectinload(Bookings.booking_passengers),
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

    async def _departure_datetime(
        self, db: AsyncSession, booking: Bookings
    ) -> datetime:
        """Scheduled departure at the user's boarding station. Unknown time →
        midnight of the journey date (understates hours-to-departure → harsher
        slab → we never promise more refund than the user will get)."""
        stmt = select(TrainStations.departure_time).where(
            TrainStations.train_id == booking.train_id,
            TrainStations.station_id == booking.source_station_id,
        )
        departure_time = (await db.execute(stmt)).scalar_one_or_none()

        hh, mm = FALLBACK_DEPARTURE_HOUR, 0
        if departure_time:
            try:
                hh, mm = int(departure_time[:2]), int(departure_time[3:5])
            except (ValueError, IndexError):
                hh, mm = FALLBACK_DEPARTURE_HOUR, 0

        return datetime(
            booking.journey_date.year,
            booking.journey_date.month,
            booking.journey_date.day,
            hh,
            mm,
            tzinfo=_IST,
        )

    async def _is_chart_prepared(self, db: AsyncSession, booking: Bookings) -> bool:
        stmt = select(SeatInventories.is_chart_prepared).where(
            SeatInventories.train_id == booking.train_id,
            SeatInventories.journey_date == booking.journey_date,
            SeatInventories.train_class == booking.train_class,
            SeatInventories.quota == booking.quota,
        )
        return bool((await db.execute(stmt)).scalar_one_or_none())

    # ── Result builders ───────────────────────────────────────────────────────

    def _base_result(self, booking: Bookings, refund: dict, signals: dict) -> dict:
        return {
            "status": AdviceStatus.ADVISED.value,
            "pnr_number": booking.pnr_number,
            "booking_status": booking.booking_status,
            "recommendation": None,
            "action": None,
            "reason": "",
            "refund": refund,
            "refund_ladder": [],
            "waitlist": None,
            "suggest_alternatives": False,
            "alternatives": [],
            "signals": signals,
            "source": AdviceSource.RULES.value,
        }

    def _terminal_result(
        self,
        advice_status: AdviceStatus,
        booking: Bookings,
        *,
        reason: str,
        hours_to_departure: float | None = None,
        is_chart_prepared: bool = False,
    ) -> dict:
        return {
            "status": advice_status.value,
            "pnr_number": booking.pnr_number,
            "booking_status": booking.booking_status,
            "recommendation": None,
            "action": None,
            "reason": reason,
            "refund": None,
            "refund_ladder": [],
            "waitlist": None,
            "suggest_alternatives": False,
            "alternatives": [],
            "signals": self._signals(booking, hours_to_departure, is_chart_prepared),
            "source": AdviceSource.RULES.value,
        }

    def _degraded_result(self, booking: Bookings, refund: dict, signals: dict) -> dict:
        """Advice computation failed — the deterministic refund preview still
        stands; degrade the advice itself to an honest MONITOR."""
        recommendation = AdviceRecommendation.MONITOR
        return self._base_result(booking, refund, signals) | {
            "recommendation": recommendation.value,
            "action": RECOMMENDATION_ACTION[recommendation],
            "reason": (
                "We couldn't generate advice right now — the refund numbers above "
                "are exact, so decide with those and re-check in a while."
            ),
        }

    def _signals(
        self,
        booking: Bookings,
        hours_to_departure: float | None,
        is_chart_prepared: bool,
    ) -> dict:
        return {
            "booking_status": booking.booking_status,
            "train_class": booking.train_class,
            "quota": booking.quota,
            "is_tatkal": booking.quota in TATKAL_QUOTAS,
            "hours_to_departure": (
                round(hours_to_departure, HOURS_DECIMALS)
                if hours_to_departure is not None
                else None
            ),
            "is_chart_prepared": is_chart_prepared,
            "journey_date": booking.journey_date.isoformat(),
        }
