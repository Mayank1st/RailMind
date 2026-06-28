from __future__ import annotations

from typing import Literal, Optional

from pydantic import Field

from app.schemas.base import BaseDTO


# -- WaitlistAlternative -------------------------------------
class WaitlistAlternativeDTO(BaseDTO):
    train_number: Optional[str] = None
    train_name: Optional[str] = None
    train_type: Optional[str] = None
    journey_date: Optional[str] = None  # ISO date; may be ±1 day from the booking
    date_offset_days: Optional[int] = None  # 0 = same date, ±1 = flexible
    departs: Optional[str] = None
    arrives: Optional[str] = None
    duration_minutes: Optional[int] = None
    availability: Optional[str] = None  # AVAILABLE | RAC | WL; null = unknown
    available_seats: Optional[int] = None  # confirmed seats left; null = unknown


# -- WaitlistSignals -----------------------------------------
class WaitlistSignalsDTO(BaseDTO):
    wl_type: Optional[str] = None  # GNWL | RLWL | PQWL | TQWL | RQWL
    current_position: Optional[int] = None  # as-of-now WL position
    booking_position: Optional[int] = None  # position at booking time
    days_to_journey: Optional[int] = None
    route_cancel_rate: Optional[float] = None  # 0.0-1.0; historical (or fallback)


# -- WaitlistPredictionResponse ------------------------------
class WaitlistPredictionResponseDTO(BaseDTO):
    status: Literal["WAITLISTED", "NOT_WAITLISTED"]
    booking_status: Optional[str] = None  # set when NOT_WAITLISTED (already CNF/RAC)
    confirmation_probability: Optional[float] = None  # 0.0-1.0; null on degrade/no-pred
    bucket: Optional[Literal["HIGH", "MEDIUM", "LOW"]] = None
    action: Optional[str] = None  # what to do, derived from the bucket
    reason: str  # human-readable; templated in L1, Gemini-enriched in L3
    signals: WaitlistSignalsDTO  # transparency — what the prediction was based on
    suggest_alternatives: bool = False  # true on LOW (planning doc §3)
    alternatives: list[WaitlistAlternativeDTO] = Field(
        default_factory=list
    )  # Phase-1 search reuse, LOW only
    source: Literal["RULES", "MODEL"] = "RULES"
    model_version: Optional[str] = None  # set only when the model (L2) decided
