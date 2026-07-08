import uuid
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import RailMindException
from app.db.models.festival_window import FestivalWindows
from app.domain.admin.admin_service.admin_audit_service import AdminAuditService
from app.domain.admin.constants.admin_audit import AuditAction, AuditTargetType
from app.domain.admin.constants.admin_holidays import (
    DEMAND_TIER_LABELS,
    ERR_HOLIDAY_NOT_FOUND,
    STATUS_ACTIVE,
    STATUS_DISABLED,
)
from app.domain.admin.dto.admin_holidays_request_dto import (
    CreateHolidayRequestDTO,
    UpdateHolidayRequestDTO,
)
from app.domain.admin.dto.admin_holidays_response_dto import HolidayItemDTO
from app.utils.logger import logger

_AUDIT_SNAPSHOT_FIELDS = (
    "name",
    "festival_date",
    "region",
    "lookahead_days",
    "lookbehind_days",
    "demand_tier",
    "is_active",
)

audit_service = AdminAuditService()


class AdminHolidaysService:
    """Config → Holiday Calendar CRUD (festival demand windows), audited.
    `get_active_festival_windows` is the read hook for the Fare/Waitlist advisors."""

    # ── Read ────────────────────────────────────────────────────────────────

    async def list_holidays(
        self,
        db: AsyncSession,
        region: Optional[str],
        demand_tier: Optional[str],
        status: Optional[str],
    ) -> list[HolidayItemDTO]:
        query = select(FestivalWindows)
        if region:
            query = query.where(FestivalWindows.region == region)
        if demand_tier:
            query = query.where(FestivalWindows.demand_tier == demand_tier)
        if status == STATUS_ACTIVE:
            query = query.where(FestivalWindows.is_active.is_(True))
        elif status == STATUS_DISABLED:
            query = query.where(FestivalWindows.is_active.is_(False))
        query = query.order_by(FestivalWindows.festival_date)

        rows = (await db.execute(query)).scalars().all()
        return [self._serialize(row) for row in rows]

    async def get_active_festival_windows(
        self, db: AsyncSession
    ) -> list[FestivalWindows]:
        """Advisor read hook — active windows only. (Consumer integration TBD.)"""
        return (
            (
                await db.execute(
                    select(FestivalWindows).where(FestivalWindows.is_active.is_(True))
                )
            )
            .scalars()
            .all()
        )

    # ── Actions (audited, super-admin) ──────────────────────────────────────

    async def create_holiday(
        self,
        payload: CreateHolidayRequestDTO,
        current_user: dict,
        ip: Optional[str],
        db: AsyncSession,
    ) -> HolidayItemDTO:
        row = FestivalWindows(
            name=payload.name,
            festival_date=payload.festival_date,
            region=payload.region,
            lookahead_days=payload.lookahead_days,
            lookbehind_days=payload.lookbehind_days,
            demand_tier=payload.demand_tier.value,
            is_active=payload.is_active,
            created_by=self._actor_uuid(current_user),
        )
        db.add(row)
        await db.flush()
        await self._audit(
            db,
            current_user,
            AuditAction.HOLIDAY_CREATED.value,
            row.id,
            before=None,
            after=self._snapshot(row),
            ip=ip,
        )
        await db.flush()
        logger.info("Holiday created id=%s name=%s", row.id, row.name)
        return self._serialize(row)

    async def update_holiday(
        self,
        holiday_id: uuid.UUID,
        payload: UpdateHolidayRequestDTO,
        current_user: dict,
        ip: Optional[str],
        db: AsyncSession,
    ) -> HolidayItemDTO:
        row = await self._load(holiday_id, db)
        changes = payload.model_dump(exclude_none=True)
        if not changes:
            return self._serialize(row)

        before = self._snapshot(row)
        for field, value in changes.items():
            setattr(row, field, value.value if hasattr(value, "value") else value)
        await db.flush()
        await self._audit(
            db,
            current_user,
            AuditAction.HOLIDAY_UPDATED.value,
            row.id,
            before=before,
            after=self._snapshot(row),
            ip=ip,
        )
        await db.flush()
        logger.info("Holiday updated id=%s", row.id)
        return self._serialize(row)

    async def delete_holiday(
        self,
        holiday_id: uuid.UUID,
        current_user: dict,
        ip: Optional[str],
        db: AsyncSession,
    ) -> dict:
        row = await self._load(holiday_id, db)
        snapshot = self._snapshot(row)
        await self._audit(
            db,
            current_user,
            AuditAction.HOLIDAY_DELETED.value,
            row.id,
            before=snapshot,
            after=None,
            ip=ip,
        )
        await db.delete(row)
        await db.flush()
        logger.info("Holiday deleted id=%s name=%s", holiday_id, snapshot["name"])
        return {"festival_window_id": str(holiday_id), "deleted": True}

    # ── Helpers ─────────────────────────────────────────────────────────────

    async def _load(self, holiday_id: uuid.UUID, db: AsyncSession) -> FestivalWindows:
        row = (
            await db.execute(
                select(FestivalWindows).where(FestivalWindows.id == holiday_id)
            )
        ).scalar_one_or_none()
        if row is None:
            raise RailMindException(
                code=ERR_HOLIDAY_NOT_FOUND,
                message="Holiday not found.",
                status_code=404,
            )
        return row

    @staticmethod
    def _actor_uuid(current_user: dict):
        sub = current_user.get("sub")
        return uuid.UUID(sub) if sub else None

    @staticmethod
    def _snapshot(row: FestivalWindows) -> dict:
        return {
            f: (str(getattr(row, f)) if f == "festival_date" else getattr(row, f))
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
            target_type=AuditTargetType.HOLIDAY.value,
            target_id=target_id,
            before=before,
            after=after,
            ip=ip,
        )

    @staticmethod
    def _serialize(row: FestivalWindows) -> HolidayItemDTO:
        return HolidayItemDTO(
            festival_window_id=str(row.id),
            name=row.name,
            festival_date=row.festival_date,
            region=row.region,
            lookahead_days=row.lookahead_days,
            lookbehind_days=row.lookbehind_days,
            window_total_days=row.lookahead_days + row.lookbehind_days + 1,
            demand_tier=row.demand_tier,
            demand_tier_label=DEMAND_TIER_LABELS.get(row.demand_tier, row.demand_tier),
            is_active=row.is_active,
            status=STATUS_ACTIVE if row.is_active else STATUS_DISABLED,
            created_at=row.created_at,
        )
