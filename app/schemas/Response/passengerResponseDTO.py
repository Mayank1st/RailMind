from uuid import UUID
from typing import Optional
from app.schemas.Response.baseResponseDTO import BaseDTO


class PassengerResponse(BaseDTO):
    id: UUID
    full_name: str
    age: int
    gender: str
    id_type: str | None
    id_number: str | None
    berth_preference: str
    is_primary: bool


class PassengerListResponse(BaseDTO):
    total: int
    passengers: list[PassengerResponse]
