import uuid
from datetime import date
from math import ceil

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db
from app.core.pagination import Params
from app.core.permissions import IsAdmin, IsAgent
from app.core.response import ok
from app.domain.admin.admin_service.admin_inventory_service import AdminInventoryService
from app.domain.admin.admin_service.admin_users_service import AdminUsersService
from app.domain.admin.constants.admin_inventory import MAX_WL_DEPTH_FILTER
from app.domain.admin.dto.admin_users_request_dto import (
    AdminKycReviewRequestDTO,
    AdminUpdateUserRequestDTO,
)

router = APIRouter(tags=["Admin Entities"])

admin_users_service = AdminUsersService()
admin_inventory_service = AdminInventoryService()


def _client_ip(request: Request) -> str | None:
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else None


# ── Users ────────────────────────────────────────────────────────────────────


@router.get("/users")
async def list_admin_users(
    search: str | None = Query(None, description="name / email / user id"),
    role: str | None = Query(None, description="USER | AGENT | ADMIN"),
    kyc_status: str | None = Query(None, description="PASSED | PENDING | FAILED"),
    params: Params = Depends(),
    current_user: dict = IsAgent,
    db: AsyncSession = Depends(get_db),
):
    items, total = await admin_users_service.list_users(
        db, search, role, kyc_status, params.page, params.size
    )
    pages = ceil(total / params.size) if params.size else 0
    return ok(
        data=items,
        message="Users fetched successfully.",
        meta={
            "total": total,
            "page": params.page,
            "size": params.size,
            "pages": pages,
        },
    )


@router.get("/users/summary")
async def get_admin_users_summary(
    current_user: dict = IsAgent,
    db: AsyncSession = Depends(get_db),
):
    data = await admin_users_service.get_users_summary(db)
    return ok(data=data, message="User summary fetched successfully.")


@router.get("/users/{user_id}")
async def get_admin_user_detail(
    user_id: uuid.UUID,
    current_user: dict = IsAgent,
    db: AsyncSession = Depends(get_db),
):
    data = await admin_users_service.get_user_detail(user_id, db)
    return ok(data=data, message="User detail fetched successfully.")


@router.patch("/users/{user_id}")
async def update_admin_user(
    user_id: uuid.UUID,
    payload: AdminUpdateUserRequestDTO,
    request: Request,
    current_user: dict = IsAdmin,
    db: AsyncSession = Depends(get_db),
):
    data = await admin_users_service.update_user(
        user_id, payload, current_user, _client_ip(request), db
    )
    return ok(data=data, message="User updated successfully.")


@router.post("/users/{user_id}/kyc")
async def review_admin_user_kyc(
    user_id: uuid.UUID,
    payload: AdminKycReviewRequestDTO,
    request: Request,
    current_user: dict = IsAdmin,
    db: AsyncSession = Depends(get_db),
):
    data = await admin_users_service.review_kyc(
        user_id, payload, current_user, _client_ip(request), db
    )
    return ok(data=data, message="KYC review saved successfully.")


# ── Waitlist & Inventory ──────────────────────────────────────────────────────


@router.get("/inventory")
async def list_admin_inventory(
    search: str | None = Query(None, description="train number / name"),
    train_class: str | None = Query(
        None, description="SL | 3A | 2A | 1A | CC | 2S | FC | 3E"
    ),
    quota: str | None = Query(None, description="GN | TQ | PT | LD | ..."),
    journey_date_from: date | None = Query(
        None, description="journey_date >= (inclusive)"
    ),
    journey_date_to: date | None = Query(
        None, description="journey_date <= (inclusive)"
    ),
    chart_prepared: bool | None = Query(
        None, description="true = prepared, false = pending"
    ),
    min_wl_depth: int | None = Query(
        None,
        ge=0,
        le=MAX_WL_DEPTH_FILTER,
        description="only journeys with WL depth >= n",
    ),
    params: Params = Depends(),
    current_user: dict = IsAgent,
    db: AsyncSession = Depends(get_db),
):
    items, total = await admin_inventory_service.list_inventory(
        db,
        search,
        train_class,
        quota,
        journey_date_from,
        journey_date_to,
        chart_prepared,
        min_wl_depth,
        params.page,
        params.size,
    )
    pages = ceil(total / params.size) if params.size else 0
    return ok(
        data=items,
        message="Inventory fetched successfully.",
        meta={
            "total": total,
            "page": params.page,
            "size": params.size,
            "pages": pages,
        },
    )
