from uuid import UUID
from typing import Optional
from app.schemas.base import BaseDTO


# -- PassengerResponse ---------------------------------------
class PassengerResponseDTO(BaseDTO):
    id: UUID
    full_name: str
    age: int
    gender: str
    id_type: str | None
    id_number: str | None
    berth_preference: str
    is_primary: bool


# -- PassengerListResponse -----------------------------------
class PassengerListResponseDTO(BaseDTO):
    total: int
    passengers: list[PassengerResponseDTO]
