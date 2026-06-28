from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

from sqlalchemy import func, select, tuple_
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.booking import Bookings
from app.db.models.train import SeatInventories, Trains
from app.domain.fare.constants.fare_advisor import (
    BOOK_NOW_FILL_RATE,
    CAN_WAIT_FILL_RATE,
    CONFIDENCE_DECIMALS,
    CONFIDENCE_FILL_SPAN,
    CONFIDENCE_HIGH,
    CONFIDENCE_LOW,
    CONFIDENCE_MEDIUM,
    FAR_JOURNEY_DAYS,
    NEAR_JOURNEY_DAYS,
    SOLD_OUT_FILL_RATE,
    URGENT_FILL_RATE,
    VELOCITY_HIGH_PER_DAY,
    VELOCITY_MODERATE_PER_DAY,
    VELOCITY_WINDOW_DAYS,
    AdvisorDecision,
    AdvisorSource,
    BookingVelocity,
)


class FareAdvisorRulesService:
    """Level-1 (rules) Book-Now-vs-Wait advisor.

    Reads live availability (SeatInventories) + recent booking velocity (Bookings)
    for a journey and turns them into BOOK_NOW / CAN_WAIT / URGENT with a confidence
    and a templated reason. Pure read path — never writes. Decisions are
    safe-biased: when the signal is unclear, lean toward BOOK_NOW (a wrong CAN_WAIT
    costs the user a missed seat / Tatkal surcharge; a wrong BOOK_NOW is cheap).
    """

    async def advise(
        self,
        db: AsyncSession,
        train_number: str,
        train_class: str,
        quota: str,
        journey_date: date,
    ) -> dict:
        sig = await self.gather_signals(
            db, train_number, train_class, quota, journey_date
        )
        if not sig["has_inventory"]:
            return self.no_inventory_result(sig["days_to_journey"], sig["velocity"])

        decision, confidence = self._decide(
            sig["available"],
            sig["fill_rate"],
            sig["wl_count"],
            sig["velocity"],
            sig["days_to_journey"],
        )
        return self.build_result(
            decision=decision,
            confidence=confidence,
            fill_rate=sig["fill_rate"],
            days_to_journey=sig["days_to_journey"],
            velocity=sig["velocity"],
            waitlist_pressure=sig["waitlist_pressure"],
        )

    # ── Shared signal gathering (reused by the L2 model service) ───────────────

    async def gather_signals(
        self,
        db: AsyncSession,
        train_number: str,
        train_class: str,
        quota: str,
        journey_date: date,
    ) -> dict:
        """Live as-of-now signals for a journey — shared by L1 (rules) and L2
        (model). `has_inventory` is False when no inventory row exists."""
        days_to_journey = (journey_date - date.today()).days
        velocity_count = await self._velocity_count(
            db, train_number, journey_date, train_class, quota
        )
        velocity = self._classify_velocity(velocity_count)
        inventory = await self._inventory(
            db, train_number, journey_date, train_class, quota
        )
        if inventory is None:
            return {
                "has_inventory": False,
                "available": None,
                "total": None,
                "wl_count": None,
                "wl_max": None,
                "fill_rate": None,
                "waitlist_pressure": None,
                "days_to_journey": days_to_journey,
                "velocity": velocity,
                "velocity_count": velocity_count,
            }
        available, total, wl_count, wl_max = inventory
        return {
            "has_inventory": True,
            "available": available,
            "total": total,
            "wl_count": wl_count,
            "wl_max": wl_max,
            "fill_rate": self._fill_rate(available, total),
            "waitlist_pressure": self._waitlist_pressure(wl_count, wl_max),
            "days_to_journey": days_to_journey,
            "velocity": velocity,
            "velocity_count": velocity_count,
        }

    def is_urgent(self, available: int, fill_rate: float, wl_count: int) -> bool:
        """URGENT availability RULE (planning doc §8.6) — shared across L1 and L2,
        checked before any forward-looking decision. Present-state critical only."""
        return available <= 0 or wl_count > 0 or fill_rate >= URGENT_FILL_RATE

    # ── Batch path (search-list scale: one set of queries for N journeys) ──────

    async def gather_signals_batch(
        self, db: AsyncSession, journeys: list[dict]
    ) -> dict:
        """Signals for many journeys in 2 queries total (inventory + velocity),
        not 2-per-journey. Keyed by (train_number, train_class, quota, date)."""
        if not journeys:
            return {}
        # Resolve train_number -> train_id first so the heavy tables are queried by
        # train_id (part of their composite index) — a tuple IN on train_number
        # (a Trains column) defeats the SeatInventories index on 16M+ rows.
        train_numbers = {j["train_number"] for j in journeys}
        tn_rows = (
            await db.execute(
                select(Trains.id, Trains.train_number).where(
                    Trains.train_number.in_(list(train_numbers))
                )
            )
        ).all()
        tn_to_id = {r.train_number: r.id for r in tn_rows}

        id_keys = [
            (
                tn_to_id[j["train_number"]],
                j["journey_date"],
                j["train_class"],
                j["quota"],
            )
            for j in journeys
            if j["train_number"] in tn_to_id
        ]

        inv_map: dict = {}
        vel_map: dict = {}
        if id_keys:
            inv_key = tuple_(
                SeatInventories.train_id,
                SeatInventories.journey_date,
                SeatInventories.train_class,
                SeatInventories.quota,
            )
            inv_stmt = select(
                SeatInventories.train_id,
                SeatInventories.journey_date,
                SeatInventories.train_class,
                SeatInventories.quota,
                SeatInventories.available_confirmed_seats,
                SeatInventories.total_confirmed_seats,
                SeatInventories.wl_count,
                SeatInventories.wl_max,
            ).where(inv_key.in_(id_keys))
            inv_map = {
                (r.train_id, r.journey_date, r.train_class, r.quota): (
                    int(r.available_confirmed_seats),
                    int(r.total_confirmed_seats),
                    int(r.wl_count),
                    int(r.wl_max),
                )
                for r in (await db.execute(inv_stmt)).all()
            }

            window_start = datetime.now(timezone.utc) - timedelta(
                days=VELOCITY_WINDOW_DAYS
            )
            vel_key = tuple_(
                Bookings.train_id,
                Bookings.journey_date,
                Bookings.train_class,
                Bookings.quota,
            )
            vel_stmt = (
                select(
                    Bookings.train_id,
                    Bookings.journey_date,
                    Bookings.train_class,
                    Bookings.quota,
                    func.count().label("cnt"),
                )
                .where(vel_key.in_(id_keys), Bookings.booked_at >= window_start)
                .group_by(
                    Bookings.train_id,
                    Bookings.journey_date,
                    Bookings.train_class,
                    Bookings.quota,
                )
            )
            vel_map = {
                (r.train_id, r.journey_date, r.train_class, r.quota): int(r.cnt)
                for r in (await db.execute(vel_stmt)).all()
            }

        today = date.today()
        out: dict = {}
        for j in journeys:
            tid = tn_to_id.get(j["train_number"])
            ik = (tid, j["journey_date"], j["train_class"], j["quota"])
            ok_key = (
                j["train_number"],
                j["train_class"],
                j["quota"],
                j["journey_date"],
            )
            vcount = vel_map.get(ik, 0)
            velocity = self._classify_velocity(vcount)
            days = (j["journey_date"] - today).days
            inv = inv_map.get(ik)
            if inv is None:
                out[ok_key] = {
                    "has_inventory": False,
                    "available": None,
                    "total": None,
                    "wl_count": None,
                    "wl_max": None,
                    "fill_rate": None,
                    "waitlist_pressure": None,
                    "days_to_journey": days,
                    "velocity": velocity,
                    "velocity_count": vcount,
                }
            else:
                available, total, wl_count, wl_max = inv
                out[ok_key] = {
                    "has_inventory": True,
                    "available": available,
                    "total": total,
                    "wl_count": wl_count,
                    "wl_max": wl_max,
                    "fill_rate": self._fill_rate(available, total),
                    "waitlist_pressure": self._waitlist_pressure(wl_count, wl_max),
                    "days_to_journey": days,
                    "velocity": velocity,
                    "velocity_count": vcount,
                }
        return out

    async def advise_batch(self, db: AsyncSession, journeys: list[dict]) -> list[dict]:
        """L1 batch — order-aligned with `journeys`."""
        sigs = await self.gather_signals_batch(db, journeys)
        out: list[dict] = []
        for j in journeys:
            sig = sigs[
                (j["train_number"], j["train_class"], j["quota"], j["journey_date"])
            ]
            if not sig["has_inventory"]:
                out.append(
                    self.no_inventory_result(sig["days_to_journey"], sig["velocity"])
                )
                continue
            decision, confidence = self._decide(
                sig["available"],
                sig["fill_rate"],
                sig["wl_count"],
                sig["velocity"],
                sig["days_to_journey"],
            )
            out.append(
                self.build_result(
                    decision,
                    confidence,
                    sig["fill_rate"],
                    sig["days_to_journey"],
                    sig["velocity"],
                    sig["waitlist_pressure"],
                )
            )
        return out

    # ── Decision logic ────────────────────────────────────────────────────────

    def _decide(
        self,
        available: int,
        fill_rate: float,
        wl_count: int,
        velocity: BookingVelocity,
        days_to_journey: int,
    ) -> tuple[AdvisorDecision, float]:
        """Safe-biased rule tree. URGENT (already waitlisting / near-full) is
        checked first, then BOOK_NOW, then CAN_WAIT; unclear cases default to a
        low-confidence BOOK_NOW. Confidence is not hardcoded — for fill-rate
        decisions it scales with how decisively the value cleared its threshold."""
        # 1. URGENT — availability rule (shared with L2 — see is_urgent / §8.6).
        if self.is_urgent(available, fill_rate, wl_count):
            return (AdvisorDecision.URGENT, CONFIDENCE_HIGH)

        # 2. BOOK_NOW — filling fast (confidence ~ distance past threshold), or
        #    strong demand close to the journey (indirect signal -> medium).
        if fill_rate >= BOOK_NOW_FILL_RATE:
            return (
                AdvisorDecision.BOOK_NOW,
                self.scaled_confidence(fill_rate, BOOK_NOW_FILL_RATE),
            )
        if velocity is BookingVelocity.HIGH and days_to_journey <= NEAR_JOURNEY_DAYS:
            return (AdvisorDecision.BOOK_NOW, CONFIDENCE_MEDIUM)

        # 3. CAN_WAIT — low fill with time still in hand (confidence ~ how far
        #    below the can-wait threshold the fill sits).
        if fill_rate < CAN_WAIT_FILL_RATE and days_to_journey > FAR_JOURNEY_DAYS:
            return (
                AdvisorDecision.CAN_WAIT,
                self.scaled_confidence(fill_rate, CAN_WAIT_FILL_RATE),
            )

        # 4. Unclear middle ground — safe-bias to BOOK_NOW, but honest low confidence.
        return (AdvisorDecision.BOOK_NOW, CONFIDENCE_LOW)

    def scaled_confidence(self, value: float, threshold: float) -> float:
        """Map a fill-rate decision to a confidence by its distance from the
        threshold that triggered it: at the boundary -> LOW, CONFIDENCE_FILL_SPAN
        past it -> HIGH. So borderline calls read as soft, decisive ones as firm."""
        frac = min(abs(value - threshold) / CONFIDENCE_FILL_SPAN, 1.0)
        confidence = CONFIDENCE_LOW + frac * (CONFIDENCE_HIGH - CONFIDENCE_LOW)
        return round(confidence, CONFIDENCE_DECIMALS)

    def no_inventory_result(
        self,
        days_to_journey: int,
        velocity: BookingVelocity,
        source: str = AdvisorSource.RULES.value,
    ) -> dict:
        """No live inventory row (date not seeded / far out). Fall back to a
        proximity heuristic at low confidence — safe-bias near the journey. The
        model path reuses this (it needs live signals it doesn't have here)."""
        if days_to_journey <= NEAR_JOURNEY_DAYS:
            decision = AdvisorDecision.BOOK_NOW
        else:
            decision = AdvisorDecision.CAN_WAIT
        return self.build_result(
            decision=decision,
            confidence=CONFIDENCE_LOW,
            fill_rate=None,
            days_to_journey=days_to_journey,
            velocity=velocity,
            waitlist_pressure=None,
            source=source,
        )

    # ── Result assembly (shared L1/L2) ────────────────────────────────────────

    def build_result(
        self,
        decision: AdvisorDecision,
        confidence: float,
        fill_rate: float | None,
        days_to_journey: int,
        velocity: BookingVelocity,
        waitlist_pressure: float | None,
        source: str = AdvisorSource.RULES.value,
    ) -> dict:
        return {
            "decision": decision.value,
            "confidence": confidence,
            "reason": self.build_reason(decision, fill_rate, days_to_journey),
            "signals": {
                "fill_rate": fill_rate,
                "days_to_journey": days_to_journey,
                "booking_velocity": velocity.value,
                "waitlist_pressure": waitlist_pressure,
            },
            "source": source,
        }

    def build_reason(
        self,
        decision: AdvisorDecision,
        fill_rate: float | None,
        days_to_journey: int,
    ) -> str:
        """Deterministic templated reason. Level-3 (Gemini) will later turn the
        decision + signals into a richer natural-language nudge."""
        # No live availability (no inventory row) — don't reference a fill %.
        if fill_rate is None:
            if decision is AdvisorDecision.CAN_WAIT:
                return (
                    f"Live seat availability isn't in yet, and the journey is "
                    f"{days_to_journey} days away — you can wait and check again closer "
                    f"to the date."
                )
            return (
                f"Live seat availability isn't in yet, and the journey is only "
                f"{days_to_journey} days away — booking early is the safer choice."
            )

        fill_pct = f"{round(fill_rate * 100)}%"
        if decision is AdvisorDecision.URGENT:
            if fill_rate >= SOLD_OUT_FILL_RATE:
                return (
                    "Confirmed seats for this class are sold out — only RAC / waitlist "
                    "booking is left. Try another class or train, or book the waitlist "
                    "if you're willing to risk it."
                )
            return (
                f"Seats are almost gone ({fill_pct} full) — book immediately or you may "
                f"fall to the waitlist / Tatkal."
            )
        if decision is AdvisorDecision.BOOK_NOW:
            return (
                f"Seats are filling fast ({fill_pct} full) with {days_to_journey} days to go "
                f"— book now to avoid the Tatkal surcharge."
            )
        return (
            f"No rush — only {fill_pct} full with {days_to_journey} days in hand. "
            f"You can safely wait."
        )

    # ── Signal math ───────────────────────────────────────────────────────────

    def _fill_rate(self, available: int, total: int) -> float:
        if total <= 0:
            return 0.0
        return round((total - available) / total, CONFIDENCE_DECIMALS)

    def _waitlist_pressure(self, wl_count: int, wl_max: int) -> float:
        if wl_max <= 0:
            return 0.0
        return round(wl_count / wl_max, CONFIDENCE_DECIMALS)

    def _classify_velocity(self, count: int) -> BookingVelocity:
        per_day = count / VELOCITY_WINDOW_DAYS if VELOCITY_WINDOW_DAYS else count
        if per_day >= VELOCITY_HIGH_PER_DAY:
            return BookingVelocity.HIGH
        if per_day >= VELOCITY_MODERATE_PER_DAY:
            return BookingVelocity.MODERATE
        return BookingVelocity.LOW

    # ── DB reads ──────────────────────────────────────────────────────────────

    async def _inventory(
        self,
        db: AsyncSession,
        train_number: str,
        journey_date: date,
        train_class: str,
        quota: str,
    ) -> tuple[int, int, int, int] | None:
        """Live availability for the journey: (available, total, wl_count, wl_max).
        None when no inventory row exists for the train/date/class/quota."""
        stmt = (
            select(
                SeatInventories.available_confirmed_seats,
                SeatInventories.total_confirmed_seats,
                SeatInventories.wl_count,
                SeatInventories.wl_max,
            )
            .join(Trains, Trains.id == SeatInventories.train_id)
            .where(
                Trains.train_number == train_number,
                SeatInventories.journey_date == journey_date,
                SeatInventories.train_class == train_class,
                SeatInventories.quota == quota,
            )
            .limit(1)
        )
        row = (await db.execute(stmt)).first()
        if row is None:
            return None
        return (
            int(row.available_confirmed_seats),
            int(row.total_confirmed_seats),
            int(row.wl_count),
            int(row.wl_max),
        )

    async def _velocity_count(
        self,
        db: AsyncSession,
        train_number: str,
        journey_date: date,
        train_class: str,
        quota: str,
    ) -> int:
        """How many bookings landed for this exact journey in the recent window —
        a proxy for current demand pressure."""
        window_start = datetime.now(timezone.utc) - timedelta(days=VELOCITY_WINDOW_DAYS)
        stmt = (
            select(func.count())
            .select_from(Bookings)
            .join(Trains, Trains.id == Bookings.train_id)
            .where(
                Trains.train_number == train_number,
                Bookings.journey_date == journey_date,
                Bookings.train_class == train_class,
                Bookings.quota == quota,
                Bookings.booked_at >= window_start,
            )
        )
        return int((await db.execute(stmt)).scalar_one())
