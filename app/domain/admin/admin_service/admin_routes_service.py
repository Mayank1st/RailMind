import uuid
from typing import Optional

from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.exceptions import RailMindException
from app.db.models.route import Routes
from app.db.models.train import Stations
from app.domain.admin.admin_service.admin_audit_service import AdminAuditService
from app.domain.admin.constants.admin_audit import AuditAction, AuditTargetType
from app.domain.admin.constants.admin_master_data import (
    ERR_NO_CHANGES,
    ERR_ROUTE_DUPLICATE,
    ERR_ROUTE_NOT_FOUND,
    ERR_SAME_SOURCE_DEST,
    ERR_STATION_REF_INVALID,
)
from app.domain.admin.dto.admin_routes_request_dto import (
    AdminCreateRouteRequestDTO,
    AdminUpdateRouteRequestDTO,
)
from app.domain.admin.dto.admin_routes_response_dto import AdminRouteSummaryDTO
from app.domain.admin.dto.admin_stations_response_dto import StationRefDTO
from app.utils.logger import logger

audit_service = AdminAuditService()


class AdminRoutesService:
    """Entities → Routes: read + audited CRUD over the `routes` master table.
    Routes have no dependents, so delete is a hard delete. Instantiated once at
    module load; every method takes the request-scoped `db` (no per-instance
    state)."""

    # ── Read ────────────────────────────────────────────────────────────────

    async def list_routes(
        self,
        db: AsyncSession,
        search: Optional[str],
        page: int,
        size: int,
    ) -> tuple[list[AdminRouteSummaryDTO], int]:
        conditions = [Routes.is_active.is_(True)]
        if search:
            like = f"%{search.strip()}%"
            station_ids = select(Stations.id).where(
                or_(
                    Stations.station_code.ilike(like),
                    Stations.station_name.ilike(like),
                )
            )
            conditions.append(
                or_(
                    Routes.corridor_name.ilike(like),
                    Routes.source_station_id.in_(station_ids),
                    Routes.destination_station_id.in_(station_ids),
                )
            )

        total = await db.scalar(
            select(func.count()).select_from(
                select(Routes.id).where(and_(*conditions)).subquery()
            )
        )
        rows = (
            (
                await db.execute(
                    select(Routes)
                    .where(and_(*conditions))
                    .options(
                        selectinload(Routes.source_station),
                        selectinload(Routes.destination_station),
                    )
                    .order_by(Routes.created_at.desc())
                    .limit(size)
                    .offset((page - 1) * size)
                )
            )
            .scalars()
            .all()
        )
        return [self._serialize(r) for r in rows], int(total or 0)

    # ── Writes (audited, super-admin only) ──────────────────────────────────

    async def create_route(
        self,
        db: AsyncSession,
        payload: AdminCreateRouteRequestDTO,
        current_user: dict,
        ip: Optional[str],
    ) -> AdminRouteSummaryDTO:
        self._ensure_distinct(payload.source_station_id, payload.destination_station_id)
        await self._ensure_stations(
            db, [payload.source_station_id, payload.destination_station_id]
        )
        await self._ensure_unique(
            db,
            payload.source_station_id,
            payload.destination_station_id,
            exclude_id=None,
        )
        route = Routes(
            source_station_id=payload.source_station_id,
            destination_station_id=payload.destination_station_id,
            corridor_name=payload.corridor_name,
            distance_km=payload.distance_km,
            zones=[z.value for z in payload.zones],
            trains_on_route=payload.trains_on_route,
        )
        db.add(route)
        await db.flush()
        route = await self._load(db, route.id)
        await self._audit(
            db,
            AuditAction.ROUTE_CREATED,
            route.id,
            current_user,
            ip,
            before=None,
            after=self._snapshot(route),
        )
        logger.info("Admin created route %s", route.id)
        return self._serialize(route)

    async def update_route(
        self,
        db: AsyncSession,
        route_id: uuid.UUID,
        payload: AdminUpdateRouteRequestDTO,
        current_user: dict,
        ip: Optional[str],
    ) -> AdminRouteSummaryDTO:
        fields = payload.model_fields_set
        if not fields:
            raise RailMindException(
                code=ERR_NO_CHANGES,
                message="Nothing to update.",
                status_code=400,
            )
        route = await self._load(db, route_id)
        before = self._snapshot(route)

        new_source = (
            payload.source_station_id
            if "source_station_id" in fields
            else route.source_station_id
        )
        new_dest = (
            payload.destination_station_id
            if "destination_station_id" in fields
            else route.destination_station_id
        )
        if "source_station_id" in fields or "destination_station_id" in fields:
            self._ensure_distinct(new_source, new_dest)
            await self._ensure_stations(db, [new_source, new_dest])
            await self._ensure_unique(db, new_source, new_dest, exclude_id=route.id)
            route.source_station_id = new_source
            route.destination_station_id = new_dest
        for field in ("corridor_name", "distance_km", "trains_on_route"):
            if field in fields:
                setattr(route, field, getattr(payload, field))
        if "zones" in fields:
            route.zones = [z.value for z in (payload.zones or [])]

        await db.flush()
        route = await self._load(db, route.id)
        await self._audit(
            db,
            AuditAction.ROUTE_UPDATED,
            route.id,
            current_user,
            ip,
            before=before,
            after=self._snapshot(route),
        )
        logger.info("Admin updated route %s", route.id)
        return self._serialize(route)

    async def delete_route(
        self,
        db: AsyncSession,
        route_id: uuid.UUID,
        current_user: dict,
        ip: Optional[str],
    ) -> None:
        route = await self._load(db, route_id)
        before = self._snapshot(route)
        await db.delete(route)
        await db.flush()
        await self._audit(
            db,
            AuditAction.ROUTE_DELETED,
            route_id,
            current_user,
            ip,
            before=before,
            after=None,
        )
        logger.info("Admin deleted route %s", route_id)

    # ── Helpers ─────────────────────────────────────────────────────────────

    async def _load(self, db: AsyncSession, route_id: uuid.UUID) -> Routes:
        route = (
            await db.execute(
                select(Routes)
                .where(Routes.id == route_id, Routes.is_active.is_(True))
                .options(
                    selectinload(Routes.source_station),
                    selectinload(Routes.destination_station),
                )
            )
        ).scalar_one_or_none()
        if route is None:
            raise RailMindException(
                code=ERR_ROUTE_NOT_FOUND,
                message="Route not found.",
                status_code=404,
            )
        return route

    @staticmethod
    def _ensure_distinct(source_id: uuid.UUID, destination_id: uuid.UUID) -> None:
        if source_id == destination_id:
            raise RailMindException(
                code=ERR_SAME_SOURCE_DEST,
                message="Source and destination stations must differ.",
                status_code=422,
            )

    async def _ensure_stations(
        self, db: AsyncSession, station_ids: list[uuid.UUID]
    ) -> None:
        wanted = set(station_ids)
        found = set(
            (
                await db.execute(
                    select(Stations.id).where(
                        Stations.id.in_(wanted), Stations.is_active.is_(True)
                    )
                )
            )
            .scalars()
            .all()
        )
        if wanted - found:
            raise RailMindException(
                code=ERR_STATION_REF_INVALID,
                message="Source or destination station does not exist.",
                status_code=422,
            )

    async def _ensure_unique(
        self,
        db: AsyncSession,
        source_id: uuid.UUID,
        destination_id: uuid.UUID,
        exclude_id: Optional[uuid.UUID],
    ) -> None:
        query = select(Routes.id).where(
            Routes.source_station_id == source_id,
            Routes.destination_station_id == destination_id,
        )
        if exclude_id is not None:
            query = query.where(Routes.id != exclude_id)
        if (await db.execute(query)).first() is not None:
            raise RailMindException(
                code=ERR_ROUTE_DUPLICATE,
                message="A route between these stations already exists.",
                status_code=409,
            )

    async def _audit(
        self,
        db: AsyncSession,
        action: AuditAction,
        target_id: uuid.UUID,
        current_user: dict,
        ip: Optional[str],
        *,
        before: Optional[dict],
        after: Optional[dict],
    ) -> None:
        await audit_service.record(
            db,
            actor_id=current_user.get("sub"),
            actor_username=current_user.get("username"),
            action=action.value,
            target_type=AuditTargetType.ROUTE.value,
            target_id=str(target_id),
            before=before,
            after=after,
            ip=ip,
        )

    @staticmethod
    def _snapshot(route: Routes) -> dict:
        return {
            "source_station_id": str(route.source_station_id),
            "destination_station_id": str(route.destination_station_id),
            "corridor_name": route.corridor_name,
            "distance_km": route.distance_km,
            "zones": list(route.zones or []),
            "trains_on_route": route.trains_on_route,
        }

    @staticmethod
    def _station_ref(station: Optional[Stations]) -> Optional[StationRefDTO]:
        if station is None:
            return None
        return StationRefDTO(
            station_id=str(station.id),
            station_code=station.station_code,
            station_name=station.station_name,
            city=station.city,
        )

    def _serialize(self, route: Routes) -> AdminRouteSummaryDTO:
        return AdminRouteSummaryDTO(
            route_id=str(route.id),
            source_station=self._station_ref(route.source_station),
            destination_station=self._station_ref(route.destination_station),
            corridor_name=route.corridor_name,
            distance_km=route.distance_km,
            zones=list(route.zones or []),
            trains_on_route=route.trains_on_route,
            is_active=route.is_active,
        )
