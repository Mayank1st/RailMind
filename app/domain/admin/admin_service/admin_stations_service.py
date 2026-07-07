import uuid
from typing import Optional

from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import RailMindException
from app.db.models.train import Stations
from app.domain.admin.admin_service.admin_audit_service import AdminAuditService
from app.domain.admin.constants.admin_audit import AuditAction, AuditTargetType
from app.domain.admin.constants.admin_master_data import (
    ERR_NO_CHANGES,
    ERR_STATION_CODE_TAKEN,
    ERR_STATION_NOT_FOUND,
)
from app.domain.admin.dto.admin_stations_request_dto import (
    AdminCreateStationRequestDTO,
    AdminUpdateStationRequestDTO,
)
from app.domain.admin.dto.admin_stations_response_dto import AdminStationSummaryDTO
from app.utils.logger import logger

audit_service = AdminAuditService()


class AdminStationsService:
    """Entities → Stations: read + audited create/update/soft-delete over the
    core `stations` master table. Instantiated once at module load; every method
    takes the request-scoped `db` session (no per-instance state)."""

    # ── Read ────────────────────────────────────────────────────────────────

    async def list_stations(
        self,
        db: AsyncSession,
        search: Optional[str],
        zone: Optional[str],
        is_operational: Optional[bool],
        page: int,
        size: int,
    ) -> tuple[list[AdminStationSummaryDTO], int]:
        conditions = [Stations.is_active.is_(True)]
        if search:
            like = f"%{search.strip()}%"
            conditions.append(
                or_(
                    Stations.station_code.ilike(like),
                    Stations.station_name.ilike(like),
                    Stations.city.ilike(like),
                )
            )
        if zone:
            conditions.append(Stations.zone == zone)
        if is_operational is not None:
            conditions.append(Stations.is_operational.is_(is_operational))

        base = select(Stations).where(and_(*conditions))
        total = await db.scalar(select(func.count()).select_from(base.subquery()))
        rows = (
            (
                await db.execute(
                    base.order_by(Stations.station_code.asc())
                    .limit(size)
                    .offset((page - 1) * size)
                )
            )
            .scalars()
            .all()
        )
        return [self._serialize(s) for s in rows], int(total or 0)

    # ── Writes (audited, super-admin only) ──────────────────────────────────

    async def create_station(
        self,
        db: AsyncSession,
        payload: AdminCreateStationRequestDTO,
        current_user: dict,
        ip: Optional[str],
    ) -> AdminStationSummaryDTO:
        await self._ensure_code_free(db, payload.station_code, exclude_id=None)
        station = Stations(
            station_code=payload.station_code,
            station_name=payload.station_name,
            city=payload.city,
            state=payload.state or "",
            zone=payload.zone.value if payload.zone else None,
            platforms=payload.platforms,
            is_operational=payload.is_operational,
        )
        db.add(station)
        await db.flush()
        await self._audit(
            db,
            AuditAction.STATION_CREATED,
            station.id,
            current_user,
            ip,
            before=None,
            after=self._snapshot(station),
        )
        logger.info("Admin created station %s", station.station_code)
        return self._serialize(station)

    async def update_station(
        self,
        db: AsyncSession,
        station_id: uuid.UUID,
        payload: AdminUpdateStationRequestDTO,
        current_user: dict,
        ip: Optional[str],
    ) -> AdminStationSummaryDTO:
        fields = payload.model_fields_set
        if not fields:
            raise RailMindException(
                code=ERR_NO_CHANGES,
                message="Nothing to update.",
                status_code=400,
            )
        station = await self._load(db, station_id)
        before = self._snapshot(station)

        if "station_code" in fields and payload.station_code != station.station_code:
            await self._ensure_code_free(
                db, payload.station_code, exclude_id=station.id
            )
            station.station_code = payload.station_code
        for field in ("station_name", "city", "state", "platforms", "is_operational"):
            if field in fields:
                setattr(station, field, getattr(payload, field))
        if "zone" in fields:
            station.zone = payload.zone.value if payload.zone else None

        await db.flush()
        await self._audit(
            db,
            AuditAction.STATION_UPDATED,
            station.id,
            current_user,
            ip,
            before=before,
            after=self._snapshot(station),
        )
        logger.info("Admin updated station %s", station.station_code)
        return self._serialize(station)

    async def delete_station(
        self,
        db: AsyncSession,
        station_id: uuid.UUID,
        current_user: dict,
        ip: Optional[str],
    ) -> None:
        station = await self._load(db, station_id)
        station.is_active = False
        await db.flush()
        await self._audit(
            db,
            AuditAction.STATION_DELETED,
            station.id,
            current_user,
            ip,
            before={"is_active": True},
            after={"is_active": False},
        )
        logger.info("Admin soft-deleted station %s", station.station_code)

    # ── Helpers ─────────────────────────────────────────────────────────────

    async def _load(self, db: AsyncSession, station_id: uuid.UUID) -> Stations:
        station = (
            await db.execute(
                select(Stations).where(
                    Stations.id == station_id, Stations.is_active.is_(True)
                )
            )
        ).scalar_one_or_none()
        if station is None:
            raise RailMindException(
                code=ERR_STATION_NOT_FOUND,
                message="Station not found.",
                status_code=404,
            )
        return station

    async def _ensure_code_free(
        self, db: AsyncSession, code: str, exclude_id: Optional[uuid.UUID]
    ) -> None:
        query = select(Stations.id).where(Stations.station_code == code)
        if exclude_id is not None:
            query = query.where(Stations.id != exclude_id)
        if (await db.execute(query)).first() is not None:
            raise RailMindException(
                code=ERR_STATION_CODE_TAKEN,
                message=f"Station code {code} is already in use.",
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
            target_type=AuditTargetType.STATION.value,
            target_id=str(target_id),
            before=before,
            after=after,
            ip=ip,
        )

    @staticmethod
    def _snapshot(station: Stations) -> dict:
        return {
            "station_code": station.station_code,
            "station_name": station.station_name,
            "city": station.city,
            "state": station.state,
            "zone": station.zone,
            "platforms": station.platforms,
            "is_operational": station.is_operational,
        }

    @staticmethod
    def _serialize(station: Stations) -> AdminStationSummaryDTO:
        return AdminStationSummaryDTO(
            station_id=str(station.id),
            station_code=station.station_code,
            station_name=station.station_name,
            city=station.city,
            state=station.state,
            zone=station.zone,
            platforms=station.platforms,
            is_operational=station.is_operational,
            is_active=station.is_active,
        )
