import uuid
from typing import Optional

from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.exceptions import RailMindException
from app.db.models.train import Stations, Trains
from app.domain.admin.admin_service.admin_audit_service import AdminAuditService
from app.domain.admin.constants.admin_audit import AuditAction, AuditTargetType
from app.domain.admin.constants.admin_master_data import (
    ERR_NO_CHANGES,
    ERR_SAME_SOURCE_DEST,
    ERR_STATION_REF_INVALID,
    ERR_TRAIN_NOT_FOUND,
    ERR_TRAIN_NUMBER_TAKEN,
    TRAIN_STATUS_ACTIVE,
    TRAIN_STATUS_PAUSED,
)
from app.domain.admin.dto.admin_stations_response_dto import StationRefDTO
from app.domain.admin.dto.admin_trains_request_dto import (
    AdminCreateTrainRequestDTO,
    AdminUpdateTrainRequestDTO,
)
from app.domain.admin.dto.admin_trains_response_dto import AdminTrainSummaryDTO
from app.utils.logger import logger

audit_service = AdminAuditService()


class AdminTrainsService:
    """Entities → Trains: read + audited create/update/soft-delete over the core
    `trains` master table. `is_paused` is the Active/Paused status; is_active is
    the soft-delete flag. Instantiated once at module load; every method takes
    the request-scoped `db` (no per-instance state)."""

    # ── Read ────────────────────────────────────────────────────────────────

    async def list_trains(
        self,
        db: AsyncSession,
        search: Optional[str],
        train_type: Optional[str],
        train_class: Optional[str],
        is_paused: Optional[bool],
        page: int,
        size: int,
    ) -> tuple[list[AdminTrainSummaryDTO], int]:
        conditions = [Trains.is_active.is_(True)]
        if search:
            like = f"%{search.strip()}%"
            conditions.append(
                or_(
                    Trains.train_number.ilike(like),
                    Trains.train_name.ilike(like),
                )
            )
        if train_type:
            conditions.append(Trains.train_type == train_type)
        if train_class:
            conditions.append(Trains.classes_offered.any(train_class))
        if is_paused is not None:
            conditions.append(Trains.is_paused.is_(is_paused))

        total = await db.scalar(
            select(func.count()).select_from(
                select(Trains.id).where(and_(*conditions)).subquery()
            )
        )
        rows = (
            (
                await db.execute(
                    select(Trains)
                    .where(and_(*conditions))
                    .options(
                        selectinload(Trains.source_station),
                        selectinload(Trains.destination_station),
                    )
                    .order_by(Trains.train_number.asc())
                    .limit(size)
                    .offset((page - 1) * size)
                )
            )
            .scalars()
            .all()
        )
        return [self._serialize(t) for t in rows], int(total or 0)

    # ── Writes (audited, super-admin only) ──────────────────────────────────

    async def create_train(
        self,
        db: AsyncSession,
        payload: AdminCreateTrainRequestDTO,
        current_user: dict,
        ip: Optional[str],
    ) -> AdminTrainSummaryDTO:
        self._ensure_distinct(payload.source_station_id, payload.destination_station_id)
        await self._ensure_stations(
            db, [payload.source_station_id, payload.destination_station_id]
        )
        await self._ensure_number_free(db, payload.train_number, exclude_id=None)
        train = Trains(
            train_number=payload.train_number,
            train_name=payload.train_name,
            train_type=payload.train_type.value,
            source_station_id=payload.source_station_id,
            destination_station_id=payload.destination_station_id,
            distance_km=payload.distance_km,
            halts=payload.halts,
            classes_offered=[c.value for c in payload.classes_offered],
            runs_on_days=[d.value for d in payload.runs_on_days],
            pantry_car=payload.pantry_car,
            is_paused=payload.is_paused,
        )
        db.add(train)
        await db.flush()
        train = await self._load(db, train.id)
        await self._audit(
            db,
            AuditAction.TRAIN_CREATED,
            train.id,
            current_user,
            ip,
            before=None,
            after=self._snapshot(train),
        )
        logger.info("Admin created train %s", train.train_number)
        return self._serialize(train)

    async def update_train(
        self,
        db: AsyncSession,
        train_id: uuid.UUID,
        payload: AdminUpdateTrainRequestDTO,
        current_user: dict,
        ip: Optional[str],
    ) -> AdminTrainSummaryDTO:
        fields = payload.model_fields_set
        if not fields:
            raise RailMindException(
                code=ERR_NO_CHANGES,
                message="Nothing to update.",
                status_code=400,
            )
        train = await self._load(db, train_id)
        before = self._snapshot(train)

        if "train_number" in fields and payload.train_number != train.train_number:
            await self._ensure_number_free(
                db, payload.train_number, exclude_id=train.id
            )
            train.train_number = payload.train_number

        new_source = (
            payload.source_station_id
            if "source_station_id" in fields
            else train.source_station_id
        )
        new_dest = (
            payload.destination_station_id
            if "destination_station_id" in fields
            else train.destination_station_id
        )
        if "source_station_id" in fields or "destination_station_id" in fields:
            self._ensure_distinct(new_source, new_dest)
            await self._ensure_stations(db, [new_source, new_dest])
            train.source_station_id = new_source
            train.destination_station_id = new_dest

        for field in ("train_name", "distance_km", "halts", "pantry_car", "is_paused"):
            if field in fields:
                setattr(train, field, getattr(payload, field))
        if "train_type" in fields:
            train.train_type = payload.train_type.value
        if "classes_offered" in fields:
            train.classes_offered = [c.value for c in (payload.classes_offered or [])]
        if "runs_on_days" in fields:
            train.runs_on_days = [d.value for d in (payload.runs_on_days or [])]

        await db.flush()
        train = await self._load(db, train.id)
        await self._audit(
            db,
            AuditAction.TRAIN_UPDATED,
            train.id,
            current_user,
            ip,
            before=before,
            after=self._snapshot(train),
        )
        logger.info("Admin updated train %s", train.train_number)
        return self._serialize(train)

    async def delete_train(
        self,
        db: AsyncSession,
        train_id: uuid.UUID,
        current_user: dict,
        ip: Optional[str],
    ) -> None:
        train = await self._load(db, train_id)
        train.is_active = False
        await db.flush()
        await self._audit(
            db,
            AuditAction.TRAIN_DELETED,
            train.id,
            current_user,
            ip,
            before={"is_active": True},
            after={"is_active": False},
        )
        logger.info("Admin soft-deleted train %s", train.train_number)

    # ── Helpers ─────────────────────────────────────────────────────────────

    async def _load(self, db: AsyncSession, train_id: uuid.UUID) -> Trains:
        train = (
            await db.execute(
                select(Trains)
                .where(Trains.id == train_id, Trains.is_active.is_(True))
                .options(
                    selectinload(Trains.source_station),
                    selectinload(Trains.destination_station),
                )
            )
        ).scalar_one_or_none()
        if train is None:
            raise RailMindException(
                code=ERR_TRAIN_NOT_FOUND,
                message="Train not found.",
                status_code=404,
            )
        return train

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

    async def _ensure_number_free(
        self, db: AsyncSession, number: str, exclude_id: Optional[uuid.UUID]
    ) -> None:
        query = select(Trains.id).where(Trains.train_number == number)
        if exclude_id is not None:
            query = query.where(Trains.id != exclude_id)
        if (await db.execute(query)).first() is not None:
            raise RailMindException(
                code=ERR_TRAIN_NUMBER_TAKEN,
                message=f"Train number {number} is already in use.",
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
            target_type=AuditTargetType.TRAIN.value,
            target_id=str(target_id),
            before=before,
            after=after,
            ip=ip,
        )

    @staticmethod
    def _snapshot(train: Trains) -> dict:
        return {
            "train_number": train.train_number,
            "train_name": train.train_name,
            "train_type": train.train_type,
            "source_station_id": str(train.source_station_id),
            "destination_station_id": str(train.destination_station_id),
            "distance_km": train.distance_km,
            "halts": train.halts,
            "classes_offered": list(train.classes_offered or []),
            "runs_on_days": list(train.runs_on_days or []),
            "pantry_car": train.pantry_car,
            "is_paused": train.is_paused,
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

    def _serialize(self, train: Trains) -> AdminTrainSummaryDTO:
        return AdminTrainSummaryDTO(
            train_id=str(train.id),
            train_number=train.train_number,
            train_name=train.train_name,
            source_station=self._station_ref(train.source_station),
            destination_station=self._station_ref(train.destination_station),
            train_type=train.train_type,
            classes_offered=list(train.classes_offered or []),
            runs_on_days=list(train.runs_on_days or []),
            distance_km=train.distance_km,
            halts=train.halts,
            pantry_car=train.pantry_car,
            is_paused=train.is_paused,
            status=TRAIN_STATUS_PAUSED if train.is_paused else TRAIN_STATUS_ACTIVE,
            is_active=train.is_active,
        )
