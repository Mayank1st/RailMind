from datetime import date, datetime

from app.schemas.base import BaseDTO


# -- Station Ref -------------------------------------------------
class StationRefDTO(BaseDTO):
    station_id: str
    station_code: str
    station_name: str
    city: str


# -- Passenger Line ----------------------------------------------
class PassengerLineDTO(BaseDTO):
    passenger_id: str
    full_name: str | None
    age: int | None
    gender: str | None
    berth_preference: str
    allotted_berth: str | None
    passenger_status: str
    fare: float


# -- Payment Line ------------------------------------------------
class PaymentLineDTO(BaseDTO):
    payment_id: str
    amount: float
    currency: str
    payment_method: str | None
    payment_status: str
    gateway: str
    gateway_order_id: str
    gateway_payment_id: str | None
    failure_reason: str | None
    failure_code: str | None
    initiated_at: datetime
    paid_at: datetime | None
    failed_at: datetime | None


# -- Refund Line -------------------------------------------------
class RefundLineDTO(BaseDTO):
    refund_id: str
    payment_id: str
    refund_amount: float
    deduction_amount: float
    original_amount: float
    currency: str
    refund_status: str
    refund_reason: str
    refund_notes: str | None
    gateway_refund_id: str | None
    failure_reason: str | None
    initiated_at: datetime
    processed_at: datetime | None
    failed_at: datetime | None


# -- Admin Booking Summary ---------------------------------------
class AdminBookingSummaryDTO(BaseDTO):
    booking_id: str
    pnr_number: str
    booking_status: str
    journey_date: date
    train_class: str
    quota: str
    total_fare: float
    booked_at: datetime
    train_number: str | None
    train_name: str | None
    source_station: StationRefDTO
    destination_station: StationRefDTO
    user_id: str
    user_name: str | None
    user_email: str | None


# -- Admin Booking Detail ----------------------------------------
class AdminBookingDetailResponseDTO(BaseDTO):
    booking_id: str
    pnr_number: str
    booking_status: str
    journey_date: date
    train_class: str
    quota: str
    total_fare: float
    booked_at: datetime
    created_at: datetime
    train_id: str
    train_number: str | None
    train_name: str | None
    source_station: StationRefDTO
    destination_station: StationRefDTO
    user_id: str
    user_name: str | None
    user_email: str | None
    user_mobile: str | None
    passengers: list[PassengerLineDTO]
    payments: list[PaymentLineDTO]
    refunds: list[RefundLineDTO]


# -- Admin Payment Summary ---------------------------------------
class AdminPaymentSummaryDTO(BaseDTO):
    payment_id: str
    booking_id: str
    pnr_number: str | None
    user_email: str | None
    amount: float
    currency: str
    payment_method: str | None
    payment_status: str
    gateway: str
    gateway_order_id: str
    gateway_payment_id: str | None
    failure_reason: str | None
    failure_code: str | None
    initiated_at: datetime
    paid_at: datetime | None
    failed_at: datetime | None


# -- Admin Refund Summary ----------------------------------------
class AdminRefundSummaryDTO(BaseDTO):
    refund_id: str
    payment_id: str
    booking_id: str
    pnr_number: str | None
    refund_amount: float
    deduction_amount: float
    original_amount: float
    currency: str
    refund_status: str
    refund_reason: str
    gateway_refund_id: str | None
    failure_reason: str | None
    initiated_at: datetime
    processed_at: datetime | None
    failed_at: datetime | None
