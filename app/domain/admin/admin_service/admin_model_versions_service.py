import uuid
from typing import Optional

from redis.asyncio import Redis
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.model_metadata import (
    artifact_exists,
    artifact_trained_at,
    load_model_metrics,
)
from app.core.advisor_flags import AdvisorState, get_advisor_state
from app.core.exceptions import RailMindException
from app.db.models.model_version import ModelVersions
from app.domain.admin.admin_service.admin_ai_control_service import (
    AdminAiControlService,
)
from app.domain.admin.admin_service.admin_audit_service import AdminAuditService
from app.domain.admin.constants.admin_ai_control import (
    ADVISOR_ORDER,
    ADVISOR_REGISTRY,
)
from app.domain.admin.constants.admin_audit import AuditAction, AuditTargetType
from app.domain.admin.constants.admin_model_versions import (
    ERR_MODEL_ADVISOR_NOT_FOUND,
    ERR_MODEL_ARTIFACT_MISSING,
    ERR_MODEL_NOT_ML_VERSION,
    ERR_MODEL_VERSION_NOT_FOUND,
    FALLBACK_LABEL_SUFFIX,
    FALLBACK_METRIC_TEXT,
    KIND_FALLBACK,
    KIND_ML,
    SERVING_STATUS_FALLBACK,
    SERVING_STATUS_LIVE,
    SERVING_STATUS_OFF,
    VERSION_STATUS_ACTIVE,
    VERSION_STATUS_ARCHIVED,
    VERSION_STATUS_FALLBACK,
    VERSION_STATUS_PREVIOUS,
)
from app.domain.admin.dto.admin_model_versions_response_dto import (
    ModelAdvisorRowDTO,
    ModelVersionHistoryDTO,
    ModelVersionItemDTO,
)
from app.utils.logger import logger

audit_service = AdminAuditService()
ai_control_service = AdminAiControlService()


class AdminModelVersionsService:
    """AI Control → Model Versions. A registry of model versions per advisor,
    seeded from the real on-disk artifacts + a rules-fallback pseudo-version.
    Activate / Force-fallback drive the SHARED advisor toggle (via
    AdminAiControlService) so this screen and Advisor Toggles never disagree.

    Note: activation only changes which version is *designated* active + the
    serving mode (ML vs fallback). A version-aware serving loader (so a different
    ML artifact actually loads) is a Phase-3 follow-up; today one ML artifact
    exists per advisor, so only that version is activatable.
    """

    # ── Read ────────────────────────────────────────────────────────────────

    async def list_active(
        self, db: AsyncSession, redis: Redis
    ) -> list[ModelAdvisorRowDTO]:
        rows: list[ModelAdvisorRowDTO] = []
        for advisor_key in ADVISOR_ORDER:
            await self._seed_advisor(db, advisor_key)
            versions = await self._advisor_versions(db, advisor_key)
            active_ml = self._active_ml(versions)
            fallback = self._fallback(versions)
            serving, in_use_label = await self._serving(
                redis, advisor_key, active_ml, fallback
            )

            if serving == SERVING_STATUS_LIVE:
                key_metric = self._metrics_summary(advisor_key, active_ml)
            else:
                key_metric = f"{FALLBACK_METRIC_TEXT} (model on standby)"

            rows.append(
                ModelAdvisorRowDTO(
                    advisor_key=advisor_key,
                    name=ADVISOR_REGISTRY[advisor_key]["name"],
                    active_version=in_use_label,
                    key_metric=key_metric,
                    serving_status=serving,
                )
            )
        return rows

    async def get_versions(
        self, db: AsyncSession, redis: Redis, advisor_key: str
    ) -> ModelVersionHistoryDTO:
        self._ensure_advisor(advisor_key)
        await self._seed_advisor(db, advisor_key)
        versions = await self._advisor_versions(db, advisor_key)
        active_ml = self._active_ml(versions)
        fallback = self._fallback(versions)
        serving, in_use_label = await self._serving(
            redis, advisor_key, active_ml, fallback
        )

        ml_versions = [v for v in versions if v.kind == KIND_ML]
        # "previous" = the most-recent non-active ML version; older ones "archived".
        non_active = sorted(
            (v for v in ml_versions if not v.is_active_ml),
            key=lambda v: (v.trained_at is not None, v.trained_at),
            reverse=True,
        )
        previous_id = non_active[0].id if non_active else None

        items = [
            self._serialize_version(advisor_key, v, in_use_label, previous_id)
            for v in versions
        ]
        return ModelVersionHistoryDTO(
            advisor_key=advisor_key,
            name=ADVISOR_REGISTRY[advisor_key]["name"],
            currently_serving=in_use_label,
            versions=items,
        )

    # ── Actions (audited, super-admin) ──────────────────────────────────────

    async def activate_version(
        self,
        advisor_key: str,
        version_label: str,
        current_user: dict,
        ip: Optional[str],
        db: AsyncSession,
        redis: Redis,
    ) -> ModelVersionHistoryDTO:
        self._ensure_advisor(advisor_key)
        await self._seed_advisor(db, advisor_key)
        versions = await self._advisor_versions(db, advisor_key)

        target = next((v for v in versions if v.version_label == version_label), None)
        if target is None:
            raise RailMindException(
                code=ERR_MODEL_VERSION_NOT_FOUND,
                message=f"Version '{version_label}' not found for {advisor_key}.",
                status_code=404,
            )
        if target.kind != KIND_ML:
            raise RailMindException(
                code=ERR_MODEL_NOT_ML_VERSION,
                message="Only ML versions can be activated; use force-fallback instead.",
                status_code=400,
            )
        if not (target.artifact_stem and artifact_exists(target.artifact_stem)):
            raise RailMindException(
                code=ERR_MODEL_ARTIFACT_MISSING,
                message=(
                    f"Artifact for '{version_label}' is not on disk — it cannot be "
                    "served yet (register the trained artifact first)."
                ),
                status_code=400,
            )

        for v in versions:
            if v.kind == KIND_ML:
                v.is_active_ml = v.id == target.id
        await db.flush()

        # serve ML (shared toggle) + audit as a model action
        await ai_control_service.apply_advisor_state(
            advisor_key, AdvisorState.ON.value, current_user, db, redis
        )
        await self._audit(
            db,
            current_user,
            AuditAction.MODEL_VERSION_ACTIVATED.value,
            advisor_key,
            after={"active_version": version_label},
            ip=ip,
        )
        await db.flush()
        logger.info("Model version activated %s -> %s", advisor_key, version_label)
        return await self.get_versions(db, redis, advisor_key)

    async def force_fallback(
        self,
        advisor_key: str,
        current_user: dict,
        ip: Optional[str],
        db: AsyncSession,
        redis: Redis,
    ) -> ModelVersionHistoryDTO:
        self._ensure_advisor(advisor_key)
        await self._seed_advisor(db, advisor_key)
        await ai_control_service.apply_advisor_state(
            advisor_key, AdvisorState.FORCE_RULES.value, current_user, db, redis
        )
        await self._audit(
            db,
            current_user,
            AuditAction.MODEL_FALLBACK_FORCED.value,
            advisor_key,
            after={"serving": KIND_FALLBACK},
            ip=ip,
        )
        await db.flush()
        logger.info("Model fallback forced for %s", advisor_key)
        return await self.get_versions(db, redis, advisor_key)

    async def register_promotion(
        self,
        advisor_key: str,
        version_label: str,
        artifact_stem: Optional[str],
        metrics: Optional[dict],
        trained_at,
        current_user: dict,
        db: AsyncSession,
        redis: Redis,
    ) -> None:
        """Register a promoted retrain candidate as the active ML version + serve
        ML (shared toggle → ON). Used by AdminRetrainService.promote. Reuses a row
        with the same label if present, else inserts one; clears other ML rows'
        active flag."""
        await self._seed_advisor(db, advisor_key)
        versions = await self._advisor_versions(db, advisor_key)
        existing = next((v for v in versions if v.version_label == version_label), None)
        if existing is None:
            existing = ModelVersions(
                advisor_key=advisor_key,
                version_label=version_label,
                kind=KIND_ML,
                artifact_stem=artifact_stem,
                metrics=metrics,
                trained_at=trained_at,
                is_active_ml=False,
            )
            db.add(existing)
            await db.flush()
            versions.append(existing)
        else:
            existing.artifact_stem = artifact_stem
            existing.metrics = metrics
            existing.trained_at = trained_at

        for v in versions:
            if v.kind == KIND_ML:
                v.is_active_ml = v.id == existing.id
        await db.flush()
        await ai_control_service.apply_advisor_state(
            advisor_key, AdvisorState.ON.value, current_user, db, redis
        )

    # ── Seeding ─────────────────────────────────────────────────────────────

    async def _seed_advisor(self, db: AsyncSession, advisor_key: str) -> None:
        existing = (
            await db.execute(
                select(ModelVersions.id)
                .where(ModelVersions.advisor_key == advisor_key)
                .limit(1)
            )
        ).first()
        if existing is not None:
            return

        meta = ADVISOR_REGISTRY[advisor_key]
        stem = meta["metrics_stem"]
        raw = load_model_metrics(stem)
        curated = {
            key: round(float(raw[key]), 2)
            for key, _ in meta["metric_fields"]
            if key in raw and isinstance(raw[key], (int, float))
        }
        db.add(
            ModelVersions(
                advisor_key=advisor_key,
                version_label=raw.get("model_version") or stem,
                kind=KIND_ML,
                artifact_stem=stem,
                metrics=curated,
                trained_at=artifact_trained_at(stem),
                is_active_ml=True,
            )
        )
        db.add(
            ModelVersions(
                advisor_key=advisor_key,
                version_label=f"{advisor_key}{FALLBACK_LABEL_SUFFIX}",
                kind=KIND_FALLBACK,
                artifact_stem=None,
                metrics=None,
                trained_at=None,
                is_active_ml=False,
            )
        )
        await db.flush()

    # ── Helpers ─────────────────────────────────────────────────────────────

    @staticmethod
    def _ensure_advisor(advisor_key: str) -> None:
        if advisor_key not in ADVISOR_REGISTRY:
            raise RailMindException(
                code=ERR_MODEL_ADVISOR_NOT_FOUND,
                message=f"Unknown advisor '{advisor_key}'.",
                status_code=404,
            )

    @staticmethod
    async def _advisor_versions(
        db: AsyncSession, advisor_key: str
    ) -> list[ModelVersions]:
        return list(
            (
                await db.execute(
                    select(ModelVersions)
                    .where(ModelVersions.advisor_key == advisor_key)
                    .order_by(ModelVersions.trained_at.desc().nullslast())
                )
            )
            .scalars()
            .all()
        )

    @staticmethod
    def _active_ml(versions: list[ModelVersions]) -> Optional[ModelVersions]:
        ml = [v for v in versions if v.kind == KIND_ML]
        return next((v for v in ml if v.is_active_ml), ml[0] if ml else None)

    @staticmethod
    def _fallback(versions: list[ModelVersions]) -> Optional[ModelVersions]:
        return next((v for v in versions if v.kind == KIND_FALLBACK), None)

    async def _serving(
        self,
        redis: Redis,
        advisor_key: str,
        active_ml: Optional[ModelVersions],
        fallback: Optional[ModelVersions],
    ) -> tuple[str, str]:
        """(serving_status, in_use_version_label) from the toggle + availability."""
        state = await get_advisor_state(redis, advisor_key)
        active_label = active_ml.version_label if active_ml else ""
        fallback_label = fallback.version_label if fallback else active_label
        if state == AdvisorState.OFF.value:
            return SERVING_STATUS_OFF, active_label
        if state == AdvisorState.ON.value and ai_control_service.is_model_available(
            advisor_key
        ):
            return SERVING_STATUS_LIVE, active_label
        # FORCE_RULES, or ON while the model artifact is unavailable -> fallback
        return SERVING_STATUS_FALLBACK, fallback_label

    def _metrics_summary(
        self, advisor_key: str, version: Optional[ModelVersions]
    ) -> str:
        if version is None or not version.metrics:
            return ""
        fields = ADVISOR_REGISTRY[advisor_key]["metric_fields"]
        parts = [
            f"{label} {version.metrics[key]}"
            for key, label in fields
            if key in version.metrics
        ]
        return " · ".join(parts)

    def _serialize_version(
        self,
        advisor_key: str,
        version: ModelVersions,
        in_use_label: str,
        previous_id,
    ) -> ModelVersionItemDTO:
        if version.kind == KIND_FALLBACK:
            status = VERSION_STATUS_FALLBACK
            summary = FALLBACK_METRIC_TEXT
            artifact_ok = False
        else:
            if version.is_active_ml:
                status = VERSION_STATUS_ACTIVE
            elif version.id == previous_id:
                status = VERSION_STATUS_PREVIOUS
            else:
                status = VERSION_STATUS_ARCHIVED
            summary = self._metrics_summary(advisor_key, version)
            artifact_ok = bool(
                version.artifact_stem and artifact_exists(version.artifact_stem)
            )

        return ModelVersionItemDTO(
            version_label=version.version_label,
            kind=version.kind,
            metrics_summary=summary,
            trained_at=version.trained_at,
            status=status,
            in_use=version.version_label == in_use_label,
            artifact_available=artifact_ok,
        )

    async def _audit(self, db, current_user, action, advisor_key, *, after, ip) -> None:
        await audit_service.record(
            db,
            actor_id=current_user.get("sub"),
            actor_username=current_user.get("username"),
            action=action,
            target_type=AuditTargetType.MODEL.value,
            target_id=advisor_key,
            before=None,
            after=after,
            ip=ip,
        )

    @staticmethod
    def _actor_uuid(current_user: dict):
        sub = current_user.get("sub")
        return uuid.UUID(sub) if sub else None
