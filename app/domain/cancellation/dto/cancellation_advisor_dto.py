from __future__ import annotations

from typing import Literal, Optional

from pydantic import Field

from app.domain.waitlist.dto.waitlist_prediction_dto import WaitlistAlternativeDTO
from app.schemas.base import BaseDTO


# -- PassengerRefund -------------------------------------------
class PassengerRefundDTO(BaseDTO):
    passenger_status: str  # CNF | RAC | WL
    fare: float  # what this passenger paid
    deduction_amount: float
    refund_amount: float
    rule: str  # RefundRule value, e.g. FLAT_CHARGE / PERCENT_25 / CLERKAGE


# -- RefundSummary ---------------------------------------------
class RefundSummaryDTO(BaseDTO):
    total_paid: float  # booking total (incl. non-refundable service charge)
    refund_amount: float  # what the user gets back if they cancel NOW
    deduction_amount: float  # total_paid - refund_amount
    per_passenger: list[PassengerRefundDTO] = Field(default_factory=list)


# -- RefundLadderStep ------------------------------------------
class RefundLadderStepDTO(BaseDTO):
    window: str  # BEFORE_48H | H48_TO_12H | H12_TO_4H | UNDER_4H
    cancel_by: Optional[str] = (
        None  # ISO datetime (IST); null = current window open-ended
    )
    refund_amount: float  # refund if cancelled within this window
    rule: str  # RefundRule value backing the number
    is_current: bool = False  # the window "now" falls into


# -- WaitlistOutlook -------------------------------------------
class WaitlistOutlookDTO(BaseDTO):
    confirmation_probability: Optional[float] = None  # from #03; null on degrade
    bucket: Optional[Literal["HIGH", "MEDIUM", "LOW"]] = None
    model_version: Optional[str] = None  # set when the WL model (L2) decided


# -- CancellationSignals ---------------------------------------
class CancellationSignalsDTO(BaseDTO):
    booking_status: Optional[str] = None
    train_class: Optional[str] = None
    quota: Optional[str] = None
    is_tatkal: Optional[bool] = None
    hours_to_departure: Optional[float] = None  # null when departure unknown
    is_chart_prepared: Optional[bool] = None
    journey_date: Optional[str] = None  # ISO date


# -- CancellationAdvisorResponse -------------------------------
class CancellationAdvisorResponseDTO(BaseDTO):
    status: Literal["ADVISED", "ALREADY_CANCELLED", "NOT_CANCELLABLE", "NOT_APPLICABLE"]
    pnr_number: str
    booking_status: Optional[str] = None
    recommendation: Optional[
        Literal["HOLD", "MONITOR", "CANCEL_NOW", "CANCEL_EARLY"]
    ] = None
    action: Optional[str] = None  # what to do, derived from the recommendation
    reason: str  # human-readable; templated by rules, LLM-enriched on ?explain
    refund: Optional[RefundSummaryDTO] = None  # null when no refund preview applies
    refund_ladder: list[RefundLadderStepDTO] = Field(
        default_factory=list
    )  # CNF timing ladder; empty for WL (clerkage is flat until 30 min before)
    waitlist: Optional[WaitlistOutlookDTO] = None  # WL branch only (#03 reuse)
    suggest_alternatives: bool = False  # true when WL outlook is LOW
    alternatives: list[WaitlistAlternativeDTO] = Field(
        default_factory=list
    )  # Phase-1 search reuse, via #03
    signals: CancellationSignalsDTO  # transparency — what the advice was based on
    source: Literal["RULES", "MODEL"] = "RULES"  # MODEL when WL outlook came from L2
