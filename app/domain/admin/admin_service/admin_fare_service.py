import uuid
from datetime import datetime, timezone

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.exceptions import RailMindException
from app.db.models.booking import FareRules
from app.db.models.fare_rule_version import FareRuleVersionItems, FareRuleVersions
from app.domain.admin.admin_service.admin_audit_service import AdminAuditService
from app.domain.admin.constants.admin_audit import AuditAction, AuditTargetType
from app.domain.admin.constants.admin_fare import (
    CLASS_DISPLAY_NAMES,
    ERR_FARE_ALREADY_PUBLISHED,
    ERR_FARE_CLASS_NOT_FOUND,
    ERR_FARE_VERSION_NOT_DRAFT,
    ERR_FARE_VERSION_NOT_FOUND,
    INITIAL_VERSION_LABEL,
    FareVersionStatus,
)
from app.domain.admin.dto.admin_fare_request_dto import (
    EditFareRuleRequestDTO,
    FarePreviewRequestDTO,
    NewFareVersionRequestDTO,
    QuickEditFareRuleRequestDTO,
)
from app.domain.admin.dto.admin_fare_response_dto import (
    FarePreviewResponseDTO,
    FareRuleItemDTO,
    FareRulesViewDTO,
    FareVersionDTO,
)
from app.domain.common.common_service.common_service import CommonService
from app.utils.logger import logger

# Every fare field copied when cloning / applying (mirrors FareRules columns).
FARE_FIELDS = (
    "base_fare_per_km",
    "reservation_charge",
    "superfast_min_charge",
    "tatkal_multiplier",
    "premium_tatkal_min_multiplier",
    "premium_tatkal_max_multiplier",
    "gst_percent",
    "minimum_fare",
)
_CLASS_ORDER = list(CLASS_DISPLAY_NAMES)

audit_service = AdminAuditService()


class AdminFareService:
    """Config → Fare Rules. Versioned editing; publishing applies a version's
    items to the live `fare_rules` table (which the booking calculator reads)
    and busts the in-memory cache. Booking/refund calc code is untouched."""

    # ── Reads ───────────────────────────────────────────────────────────────

    async def get_current_rules(self, db: AsyncSession) -> FareRulesViewDTO:
        live = await self._ensure_live_version(db)
        return self._serialize_view(live)

    async def list_versions(self, db: AsyncSession) -> list[FareVersionDTO]:
        await self._ensure_live_version(db)
        rows = (
            (
                await db.execute(
                    select(FareRuleVersions).order_by(
                        FareRuleVersions.created_at.desc()
                    )
                )
            )
            .scalars()
            .all()
        )
        return [self._serialize_version(v) for v in rows]

    async def get_version(
        self, version_id: uuid.UUID, db: AsyncSession
    ) -> FareRulesViewDTO:
        version = await self._load_version(version_id, db)
        return self._serialize_view(version)

    # ── Version lifecycle (audited, super-admin) ────────────────────────────

    async def create_version(
        self,
        payload: NewFareVersionRequestDTO,
        current_user: dict,
        ip: str | None,
        db: AsyncSession,
    ) -> FareRulesViewDTO:
        if payload.clone_from_version_id is not None:
            source = await self._load_version(payload.clone_from_version_id, db)
        else:
            source = await self._ensure_live_version(db)

        version = FareRuleVersions(
            version_label=payload.version_label,
            effective_from=payload.effective_from,
            status=FareVersionStatus.DRAFT.value,
            change_note=payload.change_note,
            created_by=self._actor_uuid(current_user),
        )
        db.add(version)
        await db.flush()
        for item in source.items:
            db.add(self._clone_item(item, version.id))
        await db.flush()

        await audit_service.record(
            db,
            actor_id=current_user.get("sub"),
            actor_username=current_user.get("username"),
            action=AuditAction.FARE_VERSION_CREATED.value,
            target_type=AuditTargetType.FARE.value,
            target_id=version.id,
            after={
                "version_label": payload.version_label,
                "effective_from": str(payload.effective_from),
                "cloned_from": str(source.id),
            },
            reason=payload.change_note,
            ip=ip,
        )
        await db.flush()
        await db.refresh(version)
        logger.info("Fare draft version created id=%s", version.id)
        return self._serialize_view(version)

    async def edit_rule(
        self,
        version_id: uuid.UUID,
        train_class: str,
        payload: EditFareRuleRequestDTO,
        current_user: dict,
        ip: str | None,
        db: AsyncSession,
    ) -> FareRuleItemDTO:
        version = await self._load_version(version_id, db)
        if version.status != FareVersionStatus.DRAFT.value:
            raise RailMindException(
                code=ERR_FARE_VERSION_NOT_DRAFT,
                message="Only a draft version can be edited.",
                status_code=409,
            )
        item = self._find_item(version, train_class)

        changes = payload.model_dump(exclude_none=True)
        before = {f: getattr(item, f) for f in changes}
        for field, value in changes.items():
            setattr(item, field, value)
        await db.flush()

        await audit_service.record(
            db,
            actor_id=current_user.get("sub"),
            actor_username=current_user.get("username"),
            action=AuditAction.FARE_RULE_EDITED.value,
            target_type=AuditTargetType.FARE.value,
            target_id=version.id,
            before={"train_class": train_class, **before},
            after={"train_class": train_class, **changes},
            ip=ip,
        )
        await db.flush()
        return self._serialize_item(item)

    async def publish_version(
        self,
        version_id: uuid.UUID,
        current_user: dict,
        ip: str | None,
        db: AsyncSession,
    ) -> FareVersionDTO:
        version = await self._load_version(version_id, db)
        if version.status != FareVersionStatus.DRAFT.value:
            raise RailMindException(
                code=ERR_FARE_ALREADY_PUBLISHED,
                message="Only a draft version can be published.",
                status_code=409,
            )

        today = datetime.now(timezone.utc).date()
        went_live = version.effective_from <= today
        if went_live:
            await self._activate(version, db)
        else:
            version.status = FareVersionStatus.SCHEDULED.value
            version.published_at = datetime.now(timezone.utc)
        await db.flush()

        await audit_service.record(
            db,
            actor_id=current_user.get("sub"),
            actor_username=current_user.get("username"),
            action=AuditAction.FARE_VERSION_PUBLISHED.value,
            target_type=AuditTargetType.FARE.value,
            target_id=version.id,
            after={
                "status": version.status,
                "effective_from": str(version.effective_from),
            },
            reason=version.change_note,
            ip=ip,
        )
        await db.flush()
        logger.info(
            "Fare version published id=%s status=%s", version.id, version.status
        )
        return self._serialize_version(version)

    async def quick_edit_live(
        self,
        train_class: str,
        payload: QuickEditFareRuleRequestDTO,
        current_user: dict,
        ip: str | None,
        db: AsyncSession,
    ) -> FareRulesViewDTO:
        """Live-view drawer "Save & version": clone the live set into a new
        version, apply this one class's edit, and publish it (effective today)."""
        live = await self._ensure_live_version(db)
        today = datetime.now(timezone.utc).date()

        version = FareRuleVersions(
            version_label=f"{live.version_label} · {train_class} {today}",
            effective_from=today,
            status=FareVersionStatus.DRAFT.value,
            change_note=payload.change_note,
            created_by=self._actor_uuid(current_user),
        )
        db.add(version)
        await db.flush()
        for item in live.items:
            db.add(self._clone_item(item, version.id))
        await db.flush()
        await db.refresh(version)

        target = self._find_item(version, train_class)
        changes = payload.model_dump(exclude_none=True, exclude={"change_note"})
        before = {f: getattr(target, f) for f in changes}
        for field, value in changes.items():
            setattr(target, field, value)

        await self._activate(version, db)
        await db.flush()

        await audit_service.record(
            db,
            actor_id=current_user.get("sub"),
            actor_username=current_user.get("username"),
            action=AuditAction.FARE_RULE_EDITED.value,
            target_type=AuditTargetType.FARE.value,
            target_id=version.id,
            before={"train_class": train_class, **before},
            after={"train_class": train_class, **changes},
            reason=payload.change_note,
            ip=ip,
        )
        await db.flush()
        return self._serialize_view(version)

    # ── Live preview (pure banner formula — no DB, no calculator) ───────────

    @staticmethod
    def preview_fare(payload: FarePreviewRequestDTO) -> FarePreviewResponseDTO:
        base_fare = round(payload.base_fare_per_km * payload.distance_km, 2)
        subtotal = base_fare + payload.reservation_charge + payload.superfast_min_charge
        multiplier = payload.tatkal_multiplier if payload.is_tatkal else 1.0
        after_tatkal = subtotal * multiplier
        gst_amount = round(after_tatkal * payload.gst_percent / 100, 2)
        return FarePreviewResponseDTO(
            distance_km=payload.distance_km,
            base_fare=base_fare,
            reservation_charge=payload.reservation_charge,
            superfast_charge=payload.superfast_min_charge,
            tatkal_multiplier=payload.tatkal_multiplier,
            tatkal_applied=payload.is_tatkal,
            gst_percent=payload.gst_percent,
            gst_amount=gst_amount,
            total_fare=round(after_tatkal + gst_amount, 2),
        )

    # ── Internals ───────────────────────────────────────────────────────────

    async def _activate(self, version: FareRuleVersions, db: AsyncSession) -> None:
        """Apply a version's items to the live fare_rules table, archive the
        previously-live version(s), mark this one LIVE, and bust the cache."""
        existing = {
            r.train_class: r
            for r in (await db.execute(select(FareRules))).scalars().all()
        }
        for item in version.items:
            row = existing.get(item.train_class)
            values = {f: getattr(item, f) for f in FARE_FIELDS}
            if row is None:
                db.add(FareRules(train_class=item.train_class, **values))
            else:
                for field, value in values.items():
                    setattr(row, field, value)

        await db.execute(
            update(FareRuleVersions)
            .where(
                FareRuleVersions.status == FareVersionStatus.LIVE.value,
                FareRuleVersions.id != version.id,
            )
            .values(status=FareVersionStatus.ARCHIVED.value)
        )
        version.status = FareVersionStatus.LIVE.value
        version.published_at = datetime.now(timezone.utc)
        await db.flush()
        CommonService.invalidate_fare_rules_cache()

    async def _ensure_live_version(self, db: AsyncSession) -> FareRuleVersions:
        live = (
            (
                await db.execute(
                    select(FareRuleVersions)
                    .where(FareRuleVersions.status == FareVersionStatus.LIVE.value)
                    .order_by(FareRuleVersions.effective_from.desc())
                )
            )
            .scalars()
            .first()
        )
        if live is not None:
            return live

        # No live version yet — snapshot the current fare_rules into an initial one.
        fare_rows = (await db.execute(select(FareRules))).scalars().all()
        version = FareRuleVersions(
            version_label=INITIAL_VERSION_LABEL,
            effective_from=datetime.now(timezone.utc).date(),
            status=FareVersionStatus.LIVE.value,
            change_note="Initial live version (snapshot of current fare rules).",
            published_at=datetime.now(timezone.utc),
        )
        db.add(version)
        await db.flush()
        for fr in fare_rows:
            db.add(
                FareRuleVersionItems(
                    version_id=version.id,
                    train_class=fr.train_class,
                    **{f: getattr(fr, f) for f in FARE_FIELDS},
                )
            )
        await db.flush()
        await db.refresh(version)
        return version

    async def _load_version(
        self, version_id: uuid.UUID, db: AsyncSession
    ) -> FareRuleVersions:
        version = (
            await db.execute(
                select(FareRuleVersions)
                .options(selectinload(FareRuleVersions.items))
                .where(FareRuleVersions.id == version_id)
            )
        ).scalar_one_or_none()
        if version is None:
            raise RailMindException(
                code=ERR_FARE_VERSION_NOT_FOUND,
                message="Fare version not found.",
                status_code=404,
            )
        return version

    def _find_item(
        self, version: FareRuleVersions, train_class: str
    ) -> FareRuleVersionItems:
        for item in version.items:
            if item.train_class == train_class:
                return item
        raise RailMindException(
            code=ERR_FARE_CLASS_NOT_FOUND,
            message=f"Class {train_class} is not in this fare version.",
            status_code=404,
        )

    @staticmethod
    def _clone_item(item: FareRuleVersionItems, version_id) -> FareRuleVersionItems:
        return FareRuleVersionItems(
            version_id=version_id,
            train_class=item.train_class,
            **{f: getattr(item, f) for f in FARE_FIELDS},
        )

    @staticmethod
    def _actor_uuid(current_user: dict):
        sub = current_user.get("sub")
        return uuid.UUID(sub) if sub else None

    # ── Serializers ──────────────────────────────────────────────────────────

    @staticmethod
    def _class_sort_key(train_class: str) -> int:
        return _CLASS_ORDER.index(train_class) if train_class in _CLASS_ORDER else 999

    def _serialize_view(self, version: FareRuleVersions) -> FareRulesViewDTO:
        items = sorted(version.items, key=lambda i: self._class_sort_key(i.train_class))
        return FareRulesViewDTO(
            version=self._serialize_version(version),
            rules=[self._serialize_item(i) for i in items],
        )

    @staticmethod
    def _serialize_version(version: FareRuleVersions) -> FareVersionDTO:
        return FareVersionDTO(
            version_id=str(version.id),
            version_label=version.version_label,
            effective_from=version.effective_from,
            status=version.status,
            change_note=version.change_note,
            published_at=version.published_at,
            is_live=version.status == FareVersionStatus.LIVE.value,
            created_at=version.created_at,
        )

    @staticmethod
    def _serialize_item(item: FareRuleVersionItems) -> FareRuleItemDTO:
        return FareRuleItemDTO(
            train_class=item.train_class,
            class_name=CLASS_DISPLAY_NAMES.get(item.train_class, item.train_class),
            base_fare_per_km=item.base_fare_per_km,
            reservation_charge=item.reservation_charge,
            superfast_min_charge=item.superfast_min_charge,
            tatkal_multiplier=item.tatkal_multiplier,
            premium_tatkal_min_multiplier=item.premium_tatkal_min_multiplier,
            premium_tatkal_max_multiplier=item.premium_tatkal_max_multiplier,
            gst_percent=item.gst_percent,
            minimum_fare=item.minimum_fare,
        )
