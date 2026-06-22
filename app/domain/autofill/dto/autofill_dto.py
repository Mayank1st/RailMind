from __future__ import annotations

from typing import Any, Literal, Optional
from uuid import UUID

from pydantic import Field
from app.schemas.base import BaseDTO

# ── Autofill ──────────────────────────────────────────────────────────────────


# -- PassengerSuggestion -------------------------------------
class PassengerSuggestionDTO(BaseDTO):
    id: UUID
    full_name: str
    age: int
    gender: str
    berth_preference: Optional[str] = None
    is_primary: bool
    booking_count: int  # how many times this passenger has been booked


# -- AutofillResponse ----------------------------------------
class AutofillResponseDTO(BaseDTO):
    preferred_class: Optional[str] = None
    preferred_berth: Optional[str] = None
    preferred_quota: Optional[str] = None
    suggested_passengers: list[PassengerSuggestionDTO] = Field(default_factory=list)

    # Confidence reflects how many past bookings the prediction is based on
    confidence: Literal["high", "medium", "low"] = "low"

    # Where the prediction came from
    source: Literal["route_history", "general_history", "default"] = "default"

    # How many bookings used to derive the suggestion
    based_on_bookings: int = 0


# ── Smart Autofill (Level 1 rules — per-field value + confidence) ─────────────


# -- FieldSuggestion -----------------------------------------
class FieldSuggestionDTO(BaseDTO):
    value: Optional[str] = None
    confidence: float = 0.0  # 0.0-1.0


# -- PassengerRefSuggestion ----------------------------------
class PassengerRefSuggestionDTO(BaseDTO):
    passenger_id: str
    full_name: str
    age: int
    gender: str
    berth: FieldSuggestionDTO  # suggested berth (history mode) value + confidence
    confidence: float  # 0.0-1.0 — how often this passenger is booked


# -- FavouriteTrain ------------------------------------------
class FavouriteTrainDTO(BaseDTO):
    train_number: str
    train_name: str
    previous_booking_count: int  # times the user booked this train on this route


# -- SmartAutofillResponse -----------------------------------
class SmartAutofillResponseDTO(BaseDTO):
    train_class: FieldSuggestionDTO
    quota: FieldSuggestionDTO
    passengers: list[PassengerRefSuggestionDTO] = Field(default_factory=list)

    # Most-booked train on this route (user+route only; independent of train_number).
    # null when the user has no prior bookings on the route.
    favourite_train: Optional[FavouriteTrainDTO] = None

    source: Literal["HISTORY", "DEFAULTS", "MODEL"] = "DEFAULTS"
    model_version: Optional[str] = None  # set only when source == MODEL
    distance_bucket: Optional[str] = None
    journey_distance_km: Optional[int] = None
    booking_count: int = 0  # total bookings the user has
    based_on_bookings: int = 0  # bookings the class suggestion was derived from
    auto_fill: bool = False  # train_class confidence >= AI_CONFIDENCE_THRESHOLD


# ── Behavior Logging ──────────────────────────────────────────────────────────


# -- BehaviorLogCreate ---------------------------------------
class BehaviorLogCreateDTO(BaseDTO):
    user_id: Optional[str] = None
    action_type: str
    action_metadata: Optional[dict[str, Any]] = None
    session_id: Optional[str] = None
    device_type: Optional[str] = None
    ip_address_hash: Optional[str] = None
