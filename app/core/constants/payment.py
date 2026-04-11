from enum import Enum

PAYMENT_TIMEOUT_SECONDS = 600         # 10 minutes
REFUND_PROCESSING_DAYS = 5

class PaymentStatus(str, Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    SUCCESS = "success"
    FAILED = "failed"
    REFUNDED = "refunded"

