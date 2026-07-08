import uuid
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import RailMindException
from app.db.models.quota_allocation import QuotaAllocations
from app.db.models.train import Trains
from app.domain.admin.admin_service.admin_audit_service import AdminAuditService
from app.domain.admin.constants.admin_audit import AuditAction, AuditTargetType
from app.domain.admin.constants.admin_quota import (
    ERR_QUOTA_CLASS_NOT_OFFERED,
    ERR_QUOTA_DUPLICATE,
    ERR_QUOTA_INVALID_SUM,
    ERR_QUOTA_NOT_FOUND,
    ERR_QUOTA_TRAIN_NOT_FOUND,
    QUOTA_TOTAL_PCT,
)
from app.domain.admin.dto.admin_quota_request_dto import (
    CreateQuotaRequestDTO,
    UpdateQuotaRequestDTO,
)
from app.domain.admin.dto.admin_quota_response_dto import QuotaItemDTO
from app.utils.logger import logger

_PCT_FIELDS = ("general_pct", "tatkal_pct", "ladies_pct", "premium_tatkal_pct")
_AUDIT_SNAPSHOT_FIELDS = ("train_id", "train_class", *_PCT_FIELDS)

audit_service = AdminAuditService()


class AdminQuotaService:
    """Config → Quota Allocation CRUD (per-train, per-class quota split), audited.

    Each row's four percentages must sum to 100. Curated config; the seat-inventory
    generator consuming these splits is a follow-up (inventory is seeded today).
    """

    # ── Read ────────────────────────────────────────────────────────────────

    async def list_quota_allocations(self, db: AsyncSession) -> list[QuotaItemDTO]:
        rows = (
            await db.execute(
                select(QuotaAllocations, Trains)
                .join(Trains, Trains.id == QuotaAllocations.train_id)
                .order_by(Trains.train_number, QuotaAllocations.train_class)
            )
        ).all()
        return [self._serialize(alloc, train) for alloc, train in rows]

    # ── Actions (audited, super-admin) ──────────────────────────────────────

    async def create_quota_allocation(
        self,
        payload: CreateQuotaRequestDTO,
        current_user: dict,
        ip: Optional[str],
        db: AsyncSession,
    ) -> QuotaItemDTO:
        train = await self._load_train(payload.train_id, db)
        self._ensure_class_offered(train, payload.train_class)
        self._validate_sum(
            payload.general_pct,
            payload.tatkal_pct,
            payload.ladies_pct,
            payload.premium_tatkal_pct,
        )
        await self._ensure_unique(db, payload.train_id, payload.train_class, None)

        row = QuotaAllocations(
            train_id=payload.train_id,
            train_class=payload.train_class,
            general_pct=payload.general_pct,
            tatkal_pct=payload.tatkal_pct,
            ladies_pct=payload.ladies_pct,
            premium_tatkal_pct=payload.premium_tatkal_pct,
            created_by=self._actor_uuid(current_user),
        )
        db.add(row)
        await db.flush()
        await self._audit(
            db,
            current_user,
            AuditAction.QUOTA_CREATED.value,
            row.id,
            before=None,
            after=self._snapshot(row),
            ip=ip,
        )
        await db.flush()
        logger.info(
            "Quota allocation created id=%s train=%s class=%s",
            row.id,
            train.train_number,
            row.train_class,
        )
        return self._serialize(row, train)

    async def update_quota_allocation(
        self,
        quota_id: uuid.UUID,
        payload: UpdateQuotaRequestDTO,
        current_user: dict,
        ip: Optional[str],
        db: AsyncSession,
    ) -> QuotaItemDTO:
        row = await self._load(quota_id, db)
        self._validate_sum(
            payload.general_pct,
            payload.tatkal_pct,
            payload.ladies_pct,
            payload.premium_tatkal_pct,
        )

        before = self._snapshot(row)
        for field in _PCT_FIELDS:
            setattr(row, field, getattr(payload, field))
        await db.flush()
        await self._audit(
            db,
            current_user,
            AuditAction.QUOTA_UPDATED.value,
            row.id,
            before=before,
            after=self._snapshot(row),
            ip=ip,
        )
        await db.flush()
        logger.info("Quota allocation updated id=%s", row.id)

        train = await self._load_train(row.train_id, db)
        return self._serialize(row, train)

    async def delete_quota_allocation(
        self,
        quota_id: uuid.UUID,
        current_user: dict,
        ip: Optional[str],
        db: AsyncSession,
    ) -> dict:
        row = await self._load(quota_id, db)
        snapshot = self._snapshot(row)
        await self._audit(
            db,
            current_user,
            AuditAction.QUOTA_DELETED.value,
            row.id,
            before=snapshot,
            after=None,
            ip=ip,
        )
        await db.delete(row)
        await db.flush()
        logger.info("Quota allocation deleted id=%s", quota_id)
        return {"quota_allocation_id": str(quota_id), "deleted": True}

    # ── Validation helpers ──────────────────────────────────────────────────

    @staticmethod
    def _validate_sum(*pcts: int) -> None:
        total = sum(pcts)
        if total != QUOTA_TOTAL_PCT:
            raise RailMindException(
                code=ERR_QUOTA_INVALID_SUM,
                message=f"Quota percentages must sum to {QUOTA_TOTAL_PCT} (got {total}).",
                status_code=400,
            )

    @staticmethod
    def _ensure_class_offered(train: Trains, train_class: str) -> None:
        # Only enforce when the train declares its classes; an empty list means
        # the composition is unknown/unseeded, so don't block on it.
        offered = train.classes_offered or []
        if offered and train_class not in offered:
            raise RailMindException(
                code=ERR_QUOTA_CLASS_NOT_OFFERED,
                message=f"Train {train.train_number} does not offer class {train_class}.",
                status_code=400,
            )

    async def _ensure_unique(
        self,
        db: AsyncSession,
        train_id: uuid.UUID,
        train_class: str,
        exclude_id: Optional[uuid.UUID],
    ) -> None:
        query = select(QuotaAllocations.id).where(
            QuotaAllocations.train_id == train_id,
            QuotaAllocations.train_class == train_class,
        )
        if exclude_id is not None:
            query = query.where(QuotaAllocations.id != exclude_id)
        if (await db.execute(query)).first() is not None:
            raise RailMindException(
                code=ERR_QUOTA_DUPLICATE,
                message=f"A quota split for this train + {train_class} already exists.",
                status_code=409,
            )

    # ── Loaders ─────────────────────────────────────────────────────────────

    async def _load(self, quota_id: uuid.UUID, db: AsyncSession) -> QuotaAllocations:
        row = (
            await db.execute(
                select(QuotaAllocations).where(QuotaAllocations.id == quota_id)
            )
        ).scalar_one_or_none()
        if row is None:
            raise RailMindException(
                code=ERR_QUOTA_NOT_FOUND,
                message="Quota allocation not found.",
                status_code=404,
            )
        return row

    async def _load_train(self, train_id: uuid.UUID, db: AsyncSession) -> Trains:
        train = (
            await db.execute(select(Trains).where(Trains.id == train_id))
        ).scalar_one_or_none()
        if train is None:
            raise RailMindException(
                code=ERR_QUOTA_TRAIN_NOT_FOUND,
                message="Train not found.",
                status_code=404,
            )
        return train

    # ── Misc helpers ────────────────────────────────────────────────────────

    @staticmethod
    def _actor_uuid(current_user: dict):
        sub = current_user.get("sub")
        return uuid.UUID(sub) if sub else None

    @staticmethod
    def _snapshot(row: QuotaAllocations) -> dict:
        return {
            f: (str(getattr(row, f)) if f == "train_id" else getattr(row, f))
            for f in _AUDIT_SNAPSHOT_FIELDS
        }

    async def _audit(
        self, db, current_user, action, target_id, *, before, after, ip
    ) -> None:
        await audit_service.record(
            db,
            actor_id=current_user.get("sub"),
            actor_username=current_user.get("username"),
            action=action,
            target_type=AuditTargetType.QUOTA.value,
            target_id=target_id,
            before=before,
            after=after,
            ip=ip,
        )

    @staticmethod
    def _serialize(row: QuotaAllocations, train: Trains) -> QuotaItemDTO:
        return QuotaItemDTO(
            quota_allocation_id=str(row.id),
            train_id=str(row.train_id),
            train_number=train.train_number,
            train_name=train.train_name,
            train_display=f"{train.train_number} {train.train_name}",
            train_class=row.train_class,
            general_pct=row.general_pct,
            tatkal_pct=row.tatkal_pct,
            ladies_pct=row.ladies_pct,
            premium_tatkal_pct=row.premium_tatkal_pct,
            total_pct=row.general_pct
            + row.tatkal_pct
            + row.ladies_pct
            + row.premium_tatkal_pct,
            created_at=row.created_at,
        )
