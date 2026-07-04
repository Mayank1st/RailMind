from __future__ import annotations

from datetime import date
from typing import Literal, Optional

from app.schemas.base import BaseDTO


# -- FareAdvisorBatchItem ------------------------------------
class FareAdvisorBatchItemDTO(BaseDTO):
    train_number: str
    train_class: str
    journey_date: date
    quota: str = "GN"


# -- AdvisorSignals ------------------------------------------
class AdvisorSignalsDTO(BaseDTO):
    fill_rate: Optional[float] = None  # 0.0-1.0; null when no live inventory
    days_to_journey: int
    booking_velocity: Literal["HIGH", "MODERATE", "LOW"]
    waitlist_pressure: Optional[float] = None  # 0.0-1.0; null when no live inventory
    nearby_holiday: Optional[str] = (
        None  # display-only; festival name near journey, else null
    )


# -- FareAdvisorResponse -------------------------------------
class FareAdvisorResponseDTO(BaseDTO):
    decision: Literal["BOOK_NOW", "CAN_WAIT", "URGENT"]
    confidence: float  # 0.0-1.0 — how sure the advisor is
    reason: str  # human-readable nudge (templated in L1; Gemini-enriched in L3)
    signals: AdvisorSignalsDTO  # transparency — what the decision was based on
    source: Literal["RULES", "MODEL"] = "RULES"
    model_version: Optional[str] = None  # set only when the model (L2) decided
