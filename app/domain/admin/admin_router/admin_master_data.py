import uuid
from math import ceil

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db
from app.core.pagination import Params
from app.core.permissions import IsAdmin, IsAgent
from app.core.response import ok
from app.domain.admin.admin_service.admin_routes_service import AdminRoutesService
from app.domain.admin.admin_service.admin_stations_service import AdminStationsService
from app.domain.admin.admin_service.admin_trains_service import AdminTrainsService
from app.domain.admin.dto.admin_routes_request_dto import (
    AdminCreateRouteRequestDTO,
    AdminUpdateRouteRequestDTO,
)
from app.domain.admin.dto.admin_stations_request_dto import (
    AdminCreateStationRequestDTO,
    AdminUpdateStationRequestDTO,
)
from app.domain.admin.dto.admin_trains_request_dto import (
    AdminCreateTrainRequestDTO,
    AdminUpdateTrainRequestDTO,
)

router = APIRouter(tags=["Admin Master Data"])

admin_trains_service = AdminTrainsService()
admin_routes_service = AdminRoutesService()
admin_stations_service = AdminStationsService()


def _client_ip(request: Request) -> str | None:
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else None


def _list_meta(total: int, params: Params) -> dict:
    return {
        "total": total,
        "page": params.page,
        "size": params.size,
        "pages": ceil(total / params.size) if params.size else 0,
    }


# ── Trains ────────────────────────────────────────────────────────────────────


@router.get("/trains")
async def list_admin_trains(
    search: str | None = Query(None, description="train number / name"),
    train_type: str | None = Query(None, description="RAJDHANI | SHATABDI | ..."),
    train_class: str | None = Query(
        None, description="offers this class: SL | 3A | ..."
    ),
    is_paused: bool | None = Query(None, description="true = paused, false = active"),
    params: Params = Depends(),
    current_user: dict = IsAgent,
    db: AsyncSession = Depends(get_db),
):
    items, total = await admin_trains_service.list_trains(
        db, search, train_type, train_class, is_paused, params.page, params.size
    )
    return ok(
        data=items,
        message="Trains fetched successfully.",
        meta=_list_meta(total, params),
    )


@router.post("/trains")
async def create_admin_train(
    payload: AdminCreateTrainRequestDTO,
    request: Request,
    current_user: dict = IsAdmin,
    db: AsyncSession = Depends(get_db),
):
    data = await admin_trains_service.create_train(
        db, payload, current_user, _client_ip(request)
    )
    return ok(data=data, message="Train created successfully.")


@router.patch("/trains/{train_id}")
async def update_admin_train(
    train_id: uuid.UUID,
    payload: AdminUpdateTrainRequestDTO,
    request: Request,
    current_user: dict = IsAdmin,
    db: AsyncSession = Depends(get_db),
):
    data = await admin_trains_service.update_train(
        db, train_id, payload, current_user, _client_ip(request)
    )
    return ok(data=data, message="Train updated successfully.")


@router.delete("/trains/{train_id}")
async def delete_admin_train(
    train_id: uuid.UUID,
    request: Request,
    current_user: dict = IsAdmin,
    db: AsyncSession = Depends(get_db),
):
    await admin_trains_service.delete_train(
        db, train_id, current_user, _client_ip(request)
    )
    return ok(message="Train deleted successfully.")


# ── Routes ────────────────────────────────────────────────────────────────────


@router.get("/routes")
async def list_admin_routes(
    search: str | None = Query(None, description="corridor / station code / name"),
    params: Params = Depends(),
    current_user: dict = IsAgent,
    db: AsyncSession = Depends(get_db),
):
    items, total = await admin_routes_service.list_routes(
        db, search, params.page, params.size
    )
    return ok(
        data=items,
        message="Routes fetched successfully.",
        meta=_list_meta(total, params),
    )


@router.post("/routes")
async def create_admin_route(
    payload: AdminCreateRouteRequestDTO,
    request: Request,
    current_user: dict = IsAdmin,
    db: AsyncSession = Depends(get_db),
):
    data = await admin_routes_service.create_route(
        db, payload, current_user, _client_ip(request)
    )
    return ok(data=data, message="Route created successfully.")


@router.patch("/routes/{route_id}")
async def update_admin_route(
    route_id: uuid.UUID,
    payload: AdminUpdateRouteRequestDTO,
    request: Request,
    current_user: dict = IsAdmin,
    db: AsyncSession = Depends(get_db),
):
    data = await admin_routes_service.update_route(
        db, route_id, payload, current_user, _client_ip(request)
    )
    return ok(data=data, message="Route updated successfully.")


@router.delete("/routes/{route_id}")
async def delete_admin_route(
    route_id: uuid.UUID,
    request: Request,
    current_user: dict = IsAdmin,
    db: AsyncSession = Depends(get_db),
):
    await admin_routes_service.delete_route(
        db, route_id, current_user, _client_ip(request)
    )
    return ok(message="Route deleted successfully.")


# ── Stations ──────────────────────────────────────────────────────────────────


@router.get("/stations")
async def list_admin_stations(
    search: str | None = Query(None, description="code / name / city"),
    zone: str | None = Query(None, description="WR | NR | ER | ..."),
    is_operational: bool | None = Query(None, description="filter by operational flag"),
    params: Params = Depends(),
    current_user: dict = IsAgent,
    db: AsyncSession = Depends(get_db),
):
    items, total = await admin_stations_service.list_stations(
        db, search, zone, is_operational, params.page, params.size
    )
    return ok(
        data=items,
        message="Stations fetched successfully.",
        meta=_list_meta(total, params),
    )


@router.post("/stations")
async def create_admin_station(
    payload: AdminCreateStationRequestDTO,
    request: Request,
    current_user: dict = IsAdmin,
    db: AsyncSession = Depends(get_db),
):
    data = await admin_stations_service.create_station(
        db, payload, current_user, _client_ip(request)
    )
    return ok(data=data, message="Station created successfully.")


@router.patch("/stations/{station_id}")
async def update_admin_station(
    station_id: uuid.UUID,
    payload: AdminUpdateStationRequestDTO,
    request: Request,
    current_user: dict = IsAdmin,
    db: AsyncSession = Depends(get_db),
):
    data = await admin_stations_service.update_station(
        db, station_id, payload, current_user, _client_ip(request)
    )
    return ok(data=data, message="Station updated successfully.")


@router.delete("/stations/{station_id}")
async def delete_admin_station(
    station_id: uuid.UUID,
    request: Request,
    current_user: dict = IsAdmin,
    db: AsyncSession = Depends(get_db),
):
    await admin_stations_service.delete_station(
        db, station_id, current_user, _client_ip(request)
    )
    return ok(message="Station deleted successfully.")
