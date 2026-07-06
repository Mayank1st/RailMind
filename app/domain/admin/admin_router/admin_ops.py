import uuid

from fastapi import APIRouter, Depends
from fastapi_filter import FilterDepends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db
from app.core.pagination import Params, paginated
from app.core.permissions import IsAdmin, IsAgent
from app.core.response import ok
from app.domain.admin.admin_service.admin_audit_service import AdminAuditService
from app.domain.admin.admin_service.admin_errors_service import AdminErrorsService
from app.domain.admin.admin_service.admin_jobs_service import AdminJobsService
from app.domain.admin.admin_service.admin_logs_service import AdminLogsService
from app.domain.admin.admin_service.admin_ops_service import AdminOpsService
from app.domain.admin.dto.admin_audit_logs_filter_dto import AdminAuditLogFilterDTO
from app.domain.admin.dto.admin_email_logs_filter_dto import AdminEmailLogFilterDTO
from app.domain.admin.dto.admin_error_logs_filter_dto import AdminErrorLogFilterDTO
from app.domain.admin.dto.admin_ops_filter_dto import (
    AdminBookingFilterDTO,
    AdminPaymentFilterDTO,
    AdminRefundFilterDTO,
)

router = APIRouter(tags=["Admin Ops"])

admin_ops_service = AdminOpsService()
admin_logs_service = AdminLogsService()
admin_jobs_service = AdminJobsService()
admin_audit_service = AdminAuditService()
admin_errors_service = AdminErrorsService()


# ── Audit log ────────────────────────────────────────────────────────────────


@router.get("/audit-logs")
async def list_admin_audit_logs(
    audit_filter: AdminAuditLogFilterDTO = FilterDepends(AdminAuditLogFilterDTO),
    params: Params = Depends(),
    current_user: dict = IsAgent,
    db: AsyncSession = Depends(get_db),
):
    page = await admin_audit_service.list_audit_logs(db, audit_filter, params)
    return paginated(page, message="Audit logs fetched successfully.")


# ── Error logs ───────────────────────────────────────────────────────────────


@router.get("/error-logs")
async def list_admin_error_logs(
    error_filter: AdminErrorLogFilterDTO = FilterDepends(AdminErrorLogFilterDTO),
    params: Params = Depends(),
    current_user: dict = IsAgent,
    db: AsyncSession = Depends(get_db),
):
    page = await admin_errors_service.list_error_logs(db, error_filter, params)
    return paginated(page, message="Error logs fetched successfully.")


@router.get("/error-logs/summary")
async def get_admin_error_logs_summary(
    error_filter: AdminErrorLogFilterDTO = FilterDepends(AdminErrorLogFilterDTO),
    current_user: dict = IsAgent,
    db: AsyncSession = Depends(get_db),
):
    data = await admin_errors_service.get_error_logs_summary(db, error_filter)
    return ok(data=data, message="Error log summary fetched successfully.")


@router.get("/error-logs/{error_log_id}")
async def get_admin_error_log_detail(
    error_log_id: uuid.UUID,
    current_user: dict = IsAgent,
    db: AsyncSession = Depends(get_db),
):
    data = await admin_errors_service.get_error_log_detail(error_log_id, db)
    return ok(data=data, message="Error log detail fetched successfully.")


# ── Bookings & PNR ───────────────────────────────────────────────────────────


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


# ── Email logs ─────────────────────────────────────────────────────────────


@router.get("/email-logs")
async def list_admin_email_logs(
    email_filter: AdminEmailLogFilterDTO = FilterDepends(AdminEmailLogFilterDTO),
    params: Params = Depends(),
    current_user: dict = IsAgent,
    db: AsyncSession = Depends(get_db),
):
    page = await admin_logs_service.list_email_logs(db, email_filter, params)
    return paginated(page, message="Email logs fetched successfully.")


@router.get("/email-logs/summary")
async def get_admin_email_logs_summary(
    email_filter: AdminEmailLogFilterDTO = FilterDepends(AdminEmailLogFilterDTO),
    current_user: dict = IsAgent,
    db: AsyncSession = Depends(get_db),
):
    data = await admin_logs_service.get_email_logs_summary(db, email_filter)
    return ok(data=data, message="Email log summary fetched successfully.")


@router.get("/email-logs/{email_log_id}")
async def get_admin_email_log_detail(
    email_log_id: uuid.UUID,
    current_user: dict = IsAgent,
    db: AsyncSession = Depends(get_db),
):
    data = await admin_logs_service.get_email_log_detail(email_log_id, db)
    return ok(data=data, message="Email log detail fetched successfully.")


@router.post("/email-logs/{email_log_id}/retry")
async def retry_admin_email_log(
    email_log_id: uuid.UUID,
    current_user: dict = IsAdmin,
    db: AsyncSession = Depends(get_db),
):
    data = await admin_logs_service.retry_email_log(email_log_id, db)
    return ok(data=data, message="Email re-enqueued successfully.")


# ── Job / cron logs ─────────────────────────────────────────────────────────


@router.get("/jobs")
async def list_admin_jobs(
    current_user: dict = IsAgent,
    db: AsyncSession = Depends(get_db),
):
    data = await admin_jobs_service.list_jobs(db)
    return ok(data=data, message="Scheduled jobs fetched successfully.")


@router.get("/jobs/summary")
async def get_admin_jobs_summary(
    current_user: dict = IsAgent,
    db: AsyncSession = Depends(get_db),
):
    data = await admin_jobs_service.get_jobs_summary(db)
    return ok(data=data, message="Job summary fetched successfully.")


@router.get("/jobs/{job_key}/runs")
async def list_admin_job_runs(
    job_key: str,
    params: Params = Depends(),
    current_user: dict = IsAgent,
    db: AsyncSession = Depends(get_db),
):
    page = await admin_jobs_service.get_job_runs(job_key, db, params)
    return paginated(page, message="Job run history fetched successfully.")


@router.post("/jobs/{job_key}/trigger")
async def trigger_admin_job(
    job_key: str,
    current_user: dict = IsAdmin,
):
    data = await admin_jobs_service.trigger_job(job_key)
    return ok(data=data, message="Job enqueued successfully.")
