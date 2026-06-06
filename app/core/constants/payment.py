from enum import Enum

PAYMENT_TIMEOUT_SECONDS = 600  # 10 minutes
REFUND_PROCESSING_DAYS = 5


class PaymentStatus(str, Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    SUCCESS = "success"
    FAILED = "failed"
    REFUNDED = "refunded"


class PaymentMethod(str, Enum):
    UPI = "UPI"
    CARD = "CARD"
    NETBANKING = "NETBANKING"
    WALLET = "WALLET"
    EMI = "EMI"
    PAY_LATER = "PAY_LATER"
    OTHER = "OTHER"


class PaymentGateway(str, Enum):
    RAZORPAY = "RAZORPAY"
    MOCK = "MOCK"


class RefundStatus(str, Enum):
    INITIATED = "INITIATED"  # Refund requested, sent to gateway
    PROCESSING = "PROCESSING"  # Gateway processing
    PROCESSED = "PROCESSED"  # Money sent back to user
    FAILED = "FAILED"  # Gateway rejected
    CANCELLED = "CANCELLED"


class RefundReason(str, Enum):
    USER_CANCELLATION = "USER_CANCELLATION"  # User cancelled booking
    TRAIN_CANCELLED = "TRAIN_CANCELLED"  # Train itself cancelled
    WAITLIST_DROPPED = "WAITLIST_DROPPED"  # WL didn't confirm by chart prep
    PAYMENT_DISPUTE = "PAYMENT_DISPUTE"  # Chargeback / dispute
    SYSTEM_ERROR = "SYSTEM_ERROR"  # Tech failure
    ADMIN_OVERRIDE = "ADMIN_OVERRIDE"
