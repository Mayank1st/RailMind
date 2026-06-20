from enum import Enum


class BookingRetryRequestStatus(str, Enum):
    PENDING = "PENDING"
    RETRYING = "RETRYING"
    SUCCESS = "SUCCESS"
    EXHAUSTED = "EXHAUSTED"


class RetryFailureReason(str, Enum):
    SEAT_UNAVAILABLE = "SEAT_UNAVAILABLE"
    PAYMENT_TIMEOUT = "PAYMENT_TIMEOUT"
