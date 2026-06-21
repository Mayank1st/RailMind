from __future__ import annotations

from datetime import date
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.pnr.pnr_service.pnr_service import PnrService
from app.domain.booking.constants.booking import BookingStatus, WaitlistType
from app.domain.train.constants.train import TrainClass

pnr_service = PnrService()

# ── Base probabilities by WL type ─────────────────────────────────────────────
_WL_TYPE_BASE = {
    "GNWL": 70,
    "RLWL": 45,
    "PQWL": 30,
    "TQWL": 10,  # never promotes to RAC
}


# ── Position adjustments ──────────────────────────────────────────────────────
def _position_adjustment(position: int) -> int:
    if position <= 10:
        return +20
    if position <= 20:
        return +5
    if position <= 40:
        return -10
    return -25


# ── Days to departure adjustments ────────────────────────────────────────────
def _days_adjustment(days: int) -> int:
    if days > 30:
        return -5  # too early, cancellations haven't started yet
    if days >= 15:
        return +5
    if days >= 7:
        return +15  # peak cancellation window
    return +20  # last week — heavy cancellations


# ── Class adjustments ─────────────────────────────────────────────────────────
_CLASS_ADJUSTMENT = {
    "SL": +5,  # most coaches, most seats
    "3E": +3,
    "3A": 0,
    "2A": -5,
    "1A": -10,  # fewest seats
    "CC": -3,
    "2S": +3,
    "FC": -8,
}


# ── Verdict labels ────────────────────────────────────────────────────────────
def _get_verdict(probability: int) -> str:
    if probability >= 75:
        return "Very likely to confirm"
    if probability >= 50:
        return "Good chance of confirmation"
    if probability >= 30:
        return "Moderate chance — monitor closely"
    return "Unlikely to confirm — consider alternatives"


# ── Confidence based on data quality ─────────────────────────────────────────
def _get_confidence(wl_type: str, days: int) -> str:
    if wl_type == WaitlistType.GNWL and days >= 3:
        return "high"
    if wl_type in (WaitlistType.RLWL, WaitlistType.PQWL) and days >= 5:
        return "medium"
    return "low"


class WaitlistPredictorService:

    async def get_waitlist_predictor_data(
        self,
        pnr_number: str,
        db: AsyncSession,
        current_user_id: str,
    ) -> dict:

        # ── Step 1: Fetch PNR data ────────────────────────────────────────────
        pnr_data = await pnr_service.get_pnr_status(pnr_number=pnr_number, db=db)

        # ── Step 2: Validate — must be a WL booking ──────────────────────────
        if pnr_data["booking_status"] != BookingStatus.WAITLISTED.value:
            return {
                "pnr_number": pnr_number,
                "booking_status": pnr_data["booking_status"],
                "message": "This booking is not on waitlist — no prediction needed.",
                "confirmation_probability": None,
                "verdict": None,
            }

        wl_type = pnr_data.get("wl_type") or WaitlistType.GNWL
        wl_position = pnr_data.get("wl_position") or 1
        train_class = pnr_data.get("train_class") or TrainClass.SLEEPER
        journey_date = pnr_data.get("journey_date")

        # ── Step 3: Days to departure ─────────────────────────────────────────
        days_to_departure = self._calc_days_to_departure(journey_date)

        # ── Step 4: Heuristic probability engine ──────────────────────────────
        base = _WL_TYPE_BASE.get(wl_type, 30)
        pos_adj = _position_adjustment(wl_position)
        days_adj = _days_adjustment(days_to_departure)
        class_adj = _CLASS_ADJUSTMENT.get(train_class, 0)

        raw_probability = base + pos_adj + days_adj + class_adj

        # Clamp between 0 and 95
        probability = max(0, min(95, raw_probability))

        # ── Step 5: Build factors list (explain the prediction) ───────────────
        factors = self._build_factors(
            wl_type, wl_position, days_to_departure, train_class
        )

        # ── Step 6: ML stub — plug in here when model is ready ───────────────
        # ml_result = await self._ml_predict(wl_type, wl_position, train_class, days_to_departure)
        # if ml_result and ml_result["confidence"] >= AI_CONFIDENCE_THRESHOLD:
        #     probability = ml_result["probability"]

        return {
            "pnr_number": pnr_number,
            "booking_status": pnr_data["booking_status"],
            "confirmation_probability": probability,
            "confidence": _get_confidence(wl_type, days_to_departure),
            "wl_type": wl_type,
            "wl_position": wl_position,
            "train_class": train_class,
            "days_to_departure": days_to_departure,
            "verdict": _get_verdict(probability),
            "factors": factors,
            "train_number": pnr_data.get("train_number"),
            "train_name": pnr_data.get("train_name"),
            "source_station_code": pnr_data.get("source_station_code"),
            "destination_station_code": pnr_data.get("destination_station_code"),
            "journey_date": journey_date,
        }

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _calc_days_to_departure(self, journey_date) -> int:
        """Calculate days remaining until journey date."""
        if not journey_date:
            return 7  # safe default

        if isinstance(journey_date, str):
            journey_dt = date.fromisoformat(journey_date)
        else:
            journey_dt = journey_date

        delta = (journey_dt - date.today()).days
        return max(0, delta)

    def _build_factors(
        self,
        wl_type: str,
        wl_position: int,
        days_to_departure: int,
        train_class: str,
    ) -> list[str]:
        factors = []

        # WL type factor
        if wl_type == WaitlistType.GNWL:
            factors.append(
                "GNWL has the highest confirmation rate among all waitlist types"
            )
        elif wl_type == WaitlistType.RQWL:
            factors.append(
                "RLWL has moderate confirmation chances — depends on intermediate passengers"
            )
        elif wl_type == WaitlistType.PQWL:
            factors.append(
                "PQWL has lower confirmation chances — pooled quota is limited"
            )
        elif wl_type == WaitlistType.TQWL:
            factors.append(
                "TQWL (Tatkal) does not promote to RAC — low confirmation chance"
            )

        # Position factor
        if wl_position <= 10:
            factors.append(f"WL position {wl_position} is very strong — top 10")
        elif wl_position <= 20:
            factors.append(f"WL position {wl_position} is within reasonable range")
        elif wl_position <= 40:
            factors.append(
                f"WL position {wl_position} needs significant cancellations to confirm"
            )
        else:
            factors.append(f"WL position {wl_position} is high — confirmation unlikely")

        # Days factor
        if days_to_departure >= 7 and days_to_departure <= 14:
            factors.append(
                f"{days_to_departure} days to departure — peak cancellation window"
            )
        elif days_to_departure < 7:
            factors.append(
                f"Only {days_to_departure} days left — last-minute cancellations possible"
            )
        elif days_to_departure > 30:
            factors.append(
                f"{days_to_departure} days to departure — too early, most cancellations happen closer to journey"
            )

        # Class factor
        if train_class == TrainClass.SLEEPER:
            factors.append(
                "Sleeper class has more coaches — higher availability chances"
            )
        elif train_class == TrainClass.AC_1_TIER:
            factors.append("1A has very limited seats — harder to confirm")

        return factors

    # ── ML stub ───────────────────────────────────────────────────────────────
    async def _ml_predict(
        self,
        wl_type: str,
        wl_position: int,
        train_class: str,
        days_to_departure: int,
    ) -> Optional[dict]:
        """
        Future: ONNX Random Forest model trained on historical WL data.
        Features: [wl_type_encoded, wl_position, class_encoded, days_to_departure,
                   train_type, day_of_week, month]
        Returns: {"probability": 73, "confidence": 0.85} or None

        from app.ai.pipelines.waitlist_predictor import WaitlistPredictorPipeline
        result = await WaitlistPredictorPipeline().predict(features)
        if result.confidence >= AI_CONFIDENCE_THRESHOLD:
            return result
        """
        return None
