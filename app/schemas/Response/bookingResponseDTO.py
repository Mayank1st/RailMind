from app.schemas.Response.baseResponseDTO import BaseDTO
from datetime import date


class GetBookingDetailsByIdResponse(BaseDTO):
    pnr_number: str
    booking_status: str
    journey_date: date
    train_class: str
    quota: str
    total_fare: float
    source_station_name: str
    destination_station_name: str
