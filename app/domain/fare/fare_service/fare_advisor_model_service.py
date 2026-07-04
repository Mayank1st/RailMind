from __future__ import annotations

from datetime import date

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.pipelines.fare_advisor_features import MODEL_VERSION, is_festival_month
from app.ai.pipelines.fare_advisor_model import FareAdvisorModel
from app.db.models.train import Trains, TrainStations
from app.domain.fare.constants.fare_advisor import (
    BOOK_NOW_FILL_RATE,
    BOOK_NOW_FLOOR_FILL_RATE,
    BOOK_NOW_P,
    CONFIDENCE_DECIMALS,
    CONFIDENCE_HIGH,
    AdvisorDecision,
    AdvisorSource,
)
from app.domain.fare.fare_service.fare_advisor_rules_service import (
    FareAdvisorRulesService,
)
from app.domain.fare.fare_service.holiday_context import nearby_holiday_name


class FareAdvisorModelService:
    """Level-2 Book-Now-vs-Wait — global XGBoost model.

    Reuses FareAdvisorRulesService for the shared live signals + the URGENT
    availability rule (§8.6, applied first in BOTH layers), then replaces only the
    forward-looking BOOK_NOW/CAN_WAIT call with the model's
    P(sells-out-within-W). Response shape matches Level 1; `source` becomes MODEL
    and `model_version` is added when the model actually runs.
    """

    def __init__(self) -> None:
        self._rules = FareAdvisorRulesService()

    @staticmethod
    def is_available() -> bool:
        return FareAdvisorModel.is_available()

    async def advise(
        self,
        db: AsyncSession,
        train_number: str,
        train_class: str,
        quota: str,
        journey_date: date,
    ) -> dict:
        sig = await self._rules.gather_signals(
            db, train_number, train_class, quota, journey_date
        )
        holiday = nearby_holiday_name(journey_date)  # display-only; never the decision
        # No live signals -> the model can't run; degrade to the rules fallback.
        if not sig["has_inventory"]:
            return self._rules.no_inventory_result(
                sig["days_to_journey"],
                sig["velocity"],
                source=AdvisorSource.RULES.value,
                nearby_holiday=holiday,
            )

        # URGENT is a present-state availability RULE — checked before the model.
        if self._rules.is_urgent(sig["available"], sig["fill_rate"], sig["wl_count"]):
            return self._rules.build_result(
                decision=AdvisorDecision.URGENT,
                confidence=CONFIDENCE_HIGH,
                fill_rate=sig["fill_rate"],
                days_to_journey=sig["days_to_journey"],
                velocity=sig["velocity"],
                waitlist_pressure=sig["waitlist_pressure"],
                source=AdvisorSource.MODEL.value,
                nearby_holiday=holiday,
            )

        # Forward-looking decision from the model's sell-out probability.
        distance_km, train_type = await self._train_context(db, train_number)
        raw = {
            "fill_rate": sig["fill_rate"],
            "booking_velocity": sig["velocity_count"],
            "waitlist_pressure": sig["waitlist_pressure"],
            "days_to_journey": sig["days_to_journey"],
            "distance_km": distance_km,
            "train_type": train_type,
            "quota": quota,
            "train_class": train_class,
            "month": journey_date.month,
            "is_weekend": journey_date.weekday() >= 5,
            "is_festival_season": is_festival_month(journey_date.month),
        }
        proba = FareAdvisorModel.predict_sellout_proba(raw)
        if proba >= BOOK_NOW_P:
            decision, confidence = AdvisorDecision.BOOK_NOW, proba
        else:
            decision, confidence = AdvisorDecision.CAN_WAIT, 1.0 - proba

        # High-fill safety floor (§8.3): a near-full journey is too risky to ever
        # advise waiting, even if the model reads slow demand. Clamp CAN_WAIT up to
        # BOOK_NOW, with a fill-based confidence (same scale L1 uses).
        if (
            decision is AdvisorDecision.CAN_WAIT
            and sig["fill_rate"] >= BOOK_NOW_FLOOR_FILL_RATE
        ):
            decision = AdvisorDecision.BOOK_NOW
            confidence = self._rules.scaled_confidence(
                sig["fill_rate"], BOOK_NOW_FILL_RATE
            )

        result = self._rules.build_result(
            decision=decision,
            confidence=round(confidence, CONFIDENCE_DECIMALS),
            fill_rate=sig["fill_rate"],
            days_to_journey=sig["days_to_journey"],
            velocity=sig["velocity"],
            waitlist_pressure=sig["waitlist_pressure"],
            source=AdvisorSource.MODEL.value,
            nearby_holiday=holiday,
        )
        result["model_version"] = MODEL_VERSION
        return result

    async def advise_batch(self, db: AsyncSession, journeys: list[dict]) -> list[dict]:
        """L2 batch — order-aligned with `journeys`. Shared signals + URGENT rule
        per journey; one batched model inference for the model-eligible ones. No
        Gemini here (badge-only / explain=false context)."""
        sigs = await self._rules.gather_signals_batch(db, journeys)
        results: list[dict | None] = [None] * len(journeys)
        model_items: list[tuple[int, dict, dict]] = []  # (index, journey, signals)

        for i, j in enumerate(journeys):
            sig = sigs[
                (j["train_number"], j["train_class"], j["quota"], j["journey_date"])
            ]
            holiday = nearby_holiday_name(j["journey_date"])
            if not sig["has_inventory"]:
                results[i] = self._rules.no_inventory_result(
                    sig["days_to_journey"],
                    sig["velocity"],
                    source=AdvisorSource.RULES.value,
                    nearby_holiday=holiday,
                )
            elif self._rules.is_urgent(
                sig["available"], sig["fill_rate"], sig["wl_count"]
            ):
                results[i] = self._rules.build_result(
                    decision=AdvisorDecision.URGENT,
                    confidence=CONFIDENCE_HIGH,
                    fill_rate=sig["fill_rate"],
                    days_to_journey=sig["days_to_journey"],
                    velocity=sig["velocity"],
                    waitlist_pressure=sig["waitlist_pressure"],
                    source=AdvisorSource.MODEL.value,
                    nearby_holiday=holiday,
                )
            else:
                model_items.append((i, j, sig))

        if model_items:
            ctx = await self._train_context_batch(
                db, {j["train_number"] for _, j, _ in model_items}
            )
            raws = []
            for _, j, sig in model_items:
                dist, train_type = ctx.get(j["train_number"], (0, "EXPRESS"))
                raws.append(
                    {
                        "fill_rate": sig["fill_rate"],
                        "booking_velocity": sig["velocity_count"],
                        "waitlist_pressure": sig["waitlist_pressure"],
                        "days_to_journey": sig["days_to_journey"],
                        "distance_km": dist,
                        "train_type": train_type,
                        "quota": j["quota"],
                        "train_class": j["train_class"],
                        "month": j["journey_date"].month,
                        "is_weekend": j["journey_date"].weekday() >= 5,
                        "is_festival_season": is_festival_month(
                            j["journey_date"].month
                        ),
                    }
                )
            probas = FareAdvisorModel.predict_sellout_proba_batch(raws)
            for (i, j, sig), proba in zip(model_items, probas):
                if proba >= BOOK_NOW_P:
                    decision, confidence = AdvisorDecision.BOOK_NOW, proba
                else:
                    decision, confidence = AdvisorDecision.CAN_WAIT, 1.0 - proba
                if (
                    decision is AdvisorDecision.CAN_WAIT
                    and sig["fill_rate"] >= BOOK_NOW_FLOOR_FILL_RATE
                ):
                    decision = AdvisorDecision.BOOK_NOW
                    confidence = self._rules.scaled_confidence(
                        sig["fill_rate"], BOOK_NOW_FILL_RATE
                    )
                result = self._rules.build_result(
                    decision=decision,
                    confidence=round(confidence, CONFIDENCE_DECIMALS),
                    fill_rate=sig["fill_rate"],
                    days_to_journey=sig["days_to_journey"],
                    velocity=sig["velocity"],
                    waitlist_pressure=sig["waitlist_pressure"],
                    source=AdvisorSource.MODEL.value,
                    nearby_holiday=nearby_holiday_name(j["journey_date"]),
                )
                result["model_version"] = MODEL_VERSION
                results[i] = result

        return [r for r in results if r is not None]

    async def _train_context_batch(
        self, db: AsyncSession, train_numbers: set[str]
    ) -> dict[str, tuple[int, str]]:
        """{train_number: (distance_km, train_type)} for many trains in one query."""
        if not train_numbers:
            return {}
        stmt = (
            select(
                Trains.train_number,
                Trains.train_type,
                func.max(TrainStations.distance_km),
            )
            .join(TrainStations, TrainStations.train_id == Trains.id)
            .where(Trains.train_number.in_(list(train_numbers)))
            .group_by(Trains.train_number, Trains.train_type)
        )
        return {
            r.train_number: (int(r[2] or 0), r.train_type or "EXPRESS")
            for r in (await db.execute(stmt)).all()
        }

    async def _train_context(
        self, db: AsyncSession, train_number: str
    ) -> tuple[int, str]:
        """Static journey context for the model: (route distance km, train_type).
        Falls back to (0, EXPRESS) when the train can't be resolved."""
        stmt = (
            select(Trains.train_type, func.max(TrainStations.distance_km))
            .join(TrainStations, TrainStations.train_id == Trains.id)
            .where(Trains.train_number == train_number)
            .group_by(Trains.train_type)
            .limit(1)
        )
        row = (await db.execute(stmt)).first()
        if row is None:
            return (0, "EXPRESS")
        return (int(row[1] or 0), row[0] or "EXPRESS")
