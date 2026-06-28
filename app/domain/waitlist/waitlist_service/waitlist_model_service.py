from __future__ import annotations

from datetime import date

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.pipelines.waitlist_predictor_features import (
    MODEL_VERSION,
    is_festival_month,
)
from app.ai.pipelines.waitlist_predictor_model import WaitlistPredictorModel
from app.db.models.train import Trains, TrainStations
from app.domain.booking.constants.booking import WaitlistType
from app.domain.waitlist.constants.waitlist_predictor import (
    DEFAULT_ROUTE_CANCEL_RATE,
    TQWL_MAX_PROB,
    PredictionSource,
)
from app.domain.waitlist.waitlist_service.waitlist_rules_service import (
    WaitlistRulesService,
)


class WaitlistModelService:
    """Level-2 waitlist confirmation predictor — global XGBoost model.

    Reuses WaitlistRulesService for route_cancel_rate + the bucket/action/reason
    assembly, and replaces only the probability with the model's P(WL -> CNF/RAC).
    The TQWL structural overlay (never reaches RAC) is applied on top of the model
    too. Response shape matches Level 1; `source` becomes MODEL and `model_version`
    is added when the model actually runs.
    """

    def __init__(self) -> None:
        self._rules = WaitlistRulesService()

    @staticmethod
    def is_available() -> bool:
        return WaitlistPredictorModel.is_available()

    async def predict(
        self,
        db: AsyncSession,
        *,
        wl_type: str,
        current_position: int,
        booking_position: int,
        days_to_journey: int,
        train_id,
        train_class: str,
        quota: str,
        journey_date: date,
    ) -> dict:
        route_cancel_rate = await self._rules._route_cancel_rate(
            db, train_id, train_class
        )
        rate_used = (
            route_cancel_rate
            if route_cancel_rate is not None
            else DEFAULT_ROUTE_CANCEL_RATE
        )
        distance_km, train_type = await self._train_context(db, train_id)

        raw = {
            "wl_position": current_position,  # serve uses the live position (§6.3)
            "wl_type": wl_type,
            "days_to_journey": days_to_journey,
            "train_class": train_class,
            "quota": quota,
            "train_type": train_type,
            "distance_km": distance_km,
            "route_cancel_rate": rate_used,
            "month": journey_date.month,
            "is_weekend": journey_date.weekday() >= 5,
            "is_festival_season": is_festival_month(journey_date.month),
        }
        probability = WaitlistPredictorModel.predict_confirm_proba(raw)

        # TQWL never reaches RAC — structural cap on top of the model (planning §4).
        if wl_type == WaitlistType.TQWL.value:
            probability = min(probability, TQWL_MAX_PROB)

        result = self._rules.build_result(
            probability=round(probability, 2),
            wl_type=wl_type,
            current_position=current_position,
            booking_position=booking_position,
            days_to_journey=days_to_journey,
            route_cancel_rate=rate_used,
            source=PredictionSource.MODEL.value,
        )
        result["model_version"] = MODEL_VERSION
        return result

    async def _train_context(self, db: AsyncSession, train_id) -> tuple[int, str]:
        """Static journey context for the model: (route distance km, train_type).
        Falls back to (0, EXPRESS) when the train can't be resolved."""
        stmt = (
            select(Trains.train_type, func.max(TrainStations.distance_km))
            .join(TrainStations, TrainStations.train_id == Trains.id)
            .where(Trains.id == train_id)
            .group_by(Trains.train_type)
            .limit(1)
        )
        row = (await db.execute(stmt)).first()
        if row is None:
            return (0, "EXPRESS")
        return (int(row[1] or 0), row[0] or "EXPRESS")
