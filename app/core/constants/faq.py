from enum import Enum


class FaqCategory(str, Enum):
    BOOKING = "BOOKING"
    REFUND = "REFUND"
    PAYMENT = "PAYMENT"
    CANCELLATION = "CANCELLATION"
    TATKAL = "TATKAL"
    PNR = "PNR"
    GENERAL = "GENERAL"
