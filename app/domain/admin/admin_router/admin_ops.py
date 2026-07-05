import uuid

from fastapi import APIRouter, Depends
from fastapi_filter import FilterDepends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db
from app.core.pagination import Params, paginated
from app.core.permissions import IsAgent
from app.core.response import ok
from app.domain.admin.admin_service.admin_ops_service import AdminOpsService
from app.domain.admin.dto.admin_ops_filter_dto import (
    AdminBookingFilterDTO,
    AdminPaymentFilterDTO,
    AdminRefundFilterDTO,
)

router = APIRouter(tags=["Admin Ops"])

admin_ops_service = AdminOpsService()


@router.get("/bookings")
async def list_admin_bookings(
    booking_filter: AdminBookingFilterDTO = FilterDepends(AdminBookingFilterDTO),
    params: Params = Depends(),
    current_user: dict = IsAgent,
    db: AsyncSession = Depends(get_db),
):
    page = await admin_ops_service.list_bookings(db, booking_filter, params)
    return paginated(page, message="Bookings fetched successfully.")


@router.get("/bookings/{booking_id}")
async def get_admin_booking_detail(
    booking_id: uuid.UUID,
    current_user: dict = IsAgent,
    db: AsyncSession = Depends(get_db),
):
    data = await admin_ops_service.get_booking_detail(booking_id, db)
    return ok(data=data, message="Booking detail fetched successfully.")


@router.get("/payments")
async def list_admin_payments(
    payment_filter: AdminPaymentFilterDTO = FilterDepends(AdminPaymentFilterDTO),
    params: Params = Depends(),
    current_user: dict = IsAgent,
    db: AsyncSession = Depends(get_db),
):
    page = await admin_ops_service.list_payments(db, payment_filter, params)
    return paginated(page, message="Payments fetched successfully.")


@router.get("/refunds")
async def list_admin_refunds(
    refund_filter: AdminRefundFilterDTO = FilterDepends(AdminRefundFilterDTO),
    params: Params = Depends(),
    current_user: dict = IsAgent,
    db: AsyncSession = Depends(get_db),
):
    page = await admin_ops_service.list_refunds(db, refund_filter, params)
    return paginated(page, message="Refunds fetched successfully.")
