from __future__ import annotations

from typing import Any, Literal, Optional
from uuid import UUID

from pydantic import BaseModel, Field
from app.schemas.base import BaseDTO

# ── Autofill ──────────────────────────────────────────────────────────────────


class PassengerSuggestion(BaseDTO):
    id: UUID
    full_name: str
    age: int
    gender: str
    berth_preference: Optional[str] = None
    is_primary: bool
    booking_count: int  # how many times this passenger has been booked


class AutofillResponse(BaseDTO):
    preferred_class: Optional[str] = None
    preferred_berth: Optional[str] = None
    preferred_quota: Optional[str] = None
    suggested_passengers: list[PassengerSuggestion] = Field(default_factory=list)

    # Confidence reflects how many past bookings the prediction is based on
    confidence: Literal["high", "medium", "low"] = "low"

    # Where the prediction came from
    source: Literal["route_history", "general_history", "default"] = "default"

    # How many bookings used to derive the suggestion
    based_on_bookings: int = 0


# ── Behavior Logging ──────────────────────────────────────────────────────────


class BehaviorLogCreate(BaseModel):
    user_id: Optional[str] = None
    action_type: str
    action_metadata: Optional[dict[str, Any]] = None
    session_id: Optional[str] = None
    device_type: Optional[str] = None
    ip_address_hash: Optional[str] = None
