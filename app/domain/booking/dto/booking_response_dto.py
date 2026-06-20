from app.schemas.base import BaseDTO
from datetime import date


# -- GetBookingDetailsByIdResponse ---------------------------
class GetBookingDetailsByIdResponseDTO(BaseDTO):
    pnr_number: str
    booking_status: str
    journey_date: date
    train_class: str
    quota: str
    total_fare: float
    source_station_name: str
    source_station_code: str
    destination_station_name: str
    destination_station_code: str
