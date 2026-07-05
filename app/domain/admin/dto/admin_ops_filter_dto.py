# Admin Ops list filters.
#
# Built on `fastapi-filter` (see app/core/filters.py). Query params auto-map to
# WHERE clauses via operator suffixes (__ilike / __in / __gte / __lte). Each
# filter defaults `order_by` to newest-first so support sees recent activity.

import uuid
from datetime import date
from typing import Optional

from app.core.filters import BaseFilter
from app.db.models.booking import Bookings
from app.db.models.payment import Payments
from app.db.models.refund import Refunds
from app.domain.admin.constants.admin_ops import (
    DEFAULT_BOOKINGS_ORDER,
    DEFAULT_PAYMENTS_ORDER,
    DEFAULT_REFUNDS_ORDER,
)
from app.domain.payment.constants.payment import (
    PaymentGateway,
    PaymentStatus,
    RefundReason,
    RefundStatus,
)


# -- AdminBookingFilter ------------------------------------------
class AdminBookingFilterDTO(BaseFilter):
    order_by: Optional[list[str]] = DEFAULT_BOOKINGS_ORDER
    pnr_number: Optional[str] = None
    pnr_number__ilike: Optional[str] = None
    booking_status: Optional[str] = None
    booking_status__in: Optional[list[str]] = None
    user_id: Optional[uuid.UUID] = None
    train_id: Optional[uuid.UUID] = None
    train_class: Optional[str] = None
    quota: Optional[str] = None
    journey_date: Optional[date] = None
    journey_date__gte: Optional[date] = None
    journey_date__lte: Optional[date] = None

    class Constants(
        BaseFilter.Constants
    ):  # naming: ignore — fastapi-filter inner class
        model = Bookings
        search_model_fields = ["pnr_number"]


# -- AdminPaymentFilter ------------------------------------------
class AdminPaymentFilterDTO(BaseFilter):
    order_by: Optional[list[str]] = DEFAULT_PAYMENTS_ORDER
    payment_status: Optional[PaymentStatus] = None
    payment_status__in: Optional[list[PaymentStatus]] = None
    gateway: Optional[PaymentGateway] = None
    booking_id: Optional[uuid.UUID] = None
    gateway_order_id: Optional[str] = None
    gateway_payment_id: Optional[str] = None

    class Constants(
        BaseFilter.Constants
    ):  # naming: ignore — fastapi-filter inner class
        model = Payments
        search_model_fields = ["gateway_order_id", "gateway_payment_id"]


# -- AdminRefundFilter -------------------------------------------
class AdminRefundFilterDTO(BaseFilter):
    order_by: Optional[list[str]] = DEFAULT_REFUNDS_ORDER
    refund_status: Optional[RefundStatus] = None
    refund_status__in: Optional[list[RefundStatus]] = None
    refund_reason: Optional[RefundReason] = None
    booking_id: Optional[uuid.UUID] = None
    payment_id: Optional[uuid.UUID] = None
    gateway_refund_id: Optional[str] = None

    class Constants(
        BaseFilter.Constants
    ):  # naming: ignore — fastapi-filter inner class
        model = Refunds
        search_model_fields = ["gateway_refund_id"]
