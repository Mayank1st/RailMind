import uuid
from typing import Optional

from redis.asyncio import Redis
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.model_metadata import load_model_metrics
from app.core.advisor_flags import (
    ADVISOR_TOGGLE_PREFIX,
    AdvisorState,
)
from app.core.exceptions import RailMindException
from app.db.models.advisor_toggle import AdvisorToggles
from app.domain.admin.admin_service.admin_audit_service import AdminAuditService
from app.domain.admin.constants.admin_audit import AuditAction, AuditTargetType
from app.domain.admin.constants.admin_ai_control import (
    ADVISOR_ORDER,
    ADVISOR_REGISTRY,
    DEFAULT_ADVISOR_STATE,
    ERR_ADVISOR_NOT_FOUND,
    SERVING_ML,
    SERVING_OFF,
    SERVING_RULES,
    STATE_LABELS,
    STATUS_DEGRADED,
    STATUS_LIVE,
    STATUS_OFF,
)
from app.domain.admin.dto.admin_ai_control_response_dto import AdvisorToggleItemDTO
from app.domain.autofill.autofill_service.autofill_model_service import (
    AutofillModelService,
)
from app.domain.fare.fare_service.fare_advisor_model_service import (
    FareAdvisorModelService,
)
from app.domain.waitlist.waitlist_service.waitlist_model_service import (
    WaitlistModelService,
)
from app.utils.logger import logger

audit_service = AdminAuditService()


class AdminAiControlService:
    """AI Control → Advisor Toggles. Reads each advisor's 3-state flag (DB, with
    an ON default) plus live model metadata, and sets the flag — mirroring every
    change into Redis so the advisor hot-path applies it immediately. Audited."""

    def __init__(self) -> None:
        # advisor_key → model-availability probe (artifact present + loadable)
        waitlist_model_service = WaitlistModelService()
        self._availability = {
            "fare": FareAdvisorModelService.is_available,
            "waitlist": waitlist_model_service.is_available,
            "autofill": AutofillModelService().is_available,
            "cancellation": waitlist_model_service.is_available,
        }

    # ── Read ────────────────────────────────────────────────────────────────

    async def list_advisors(
        self, db: AsyncSession, redis: Redis
    ) -> list[AdvisorToggleItemDTO]:
        states = await self._load_states(db)
        items: list[AdvisorToggleItemDTO] = []
        for advisor_key in ADVISOR_ORDER:
            state = states.get(advisor_key, DEFAULT_ADVISOR_STATE)
            # keep the hot-path Redis mirror warm (survives a flush once viewed)
            await self._write_cache(redis, advisor_key, state)
            items.append(self._build_item(advisor_key, state))
        return items

    # ── Action (audited, super-admin) ───────────────────────────────────────

    async def apply_advisor_state(
        self,
        advisor_key: str,
        state: str,
        current_user: dict,
        db: AsyncSession,
        redis: Redis,
    ) -> str:
        """Upsert the advisor's toggle row + mirror to Redis (no audit). Shared by
        the Advisor Toggles screen and the Model Versions screen so both write the
        serving flag identically. Returns the previous state."""
        if advisor_key not in ADVISOR_REGISTRY:
            raise RailMindException(
                code=ERR_ADVISOR_NOT_FOUND,
                message=f"Unknown advisor '{advisor_key}'.",
                status_code=404,
            )

        row = (
            await db.execute(
                select(AdvisorToggles).where(AdvisorToggles.advisor_key == advisor_key)
            )
        ).scalar_one_or_none()

        before_state = row.state if row else DEFAULT_ADVISOR_STATE
        if row is None:
            row = AdvisorToggles(
                advisor_key=advisor_key,
                state=state,
                created_by=self._actor_uuid(current_user),
            )
            db.add(row)
        else:
            row.state = state
        await db.flush()
        await self._write_cache(redis, advisor_key, state)
        return before_state

    async def set_advisor_state(
        self,
        advisor_key: str,
        state: str,
        current_user: dict,
        ip: Optional[str],
        db: AsyncSession,
        redis: Redis,
    ) -> AdvisorToggleItemDTO:
        before_state = await self.apply_advisor_state(
            advisor_key, state, current_user, db, redis
        )
        await audit_service.record(
            db,
            actor_id=current_user.get("sub"),
            actor_username=current_user.get("username"),
            action=AuditAction.ADVISOR_STATE_CHANGED.value,
            target_type=AuditTargetType.ADVISOR.value,
            target_id=advisor_key,
            before={"state": before_state},
            after={"state": state},
            ip=ip,
        )
        await db.flush()

        logger.info("Advisor toggle %s: %s -> %s", advisor_key, before_state, state)
        return self._build_item(advisor_key, state)

    # ── Helpers ─────────────────────────────────────────────────────────────

    @staticmethod
    async def _load_states(db: AsyncSession) -> dict[str, str]:
        rows = (await db.execute(select(AdvisorToggles))).scalars().all()
        return {row.advisor_key: row.state for row in rows}

    @staticmethod
    async def _write_cache(redis: Redis, advisor_key: str, state: str) -> None:
        try:
            await redis.set(f"{ADVISOR_TOGGLE_PREFIX}{advisor_key}", state)
        except Exception:
            logger.warning("advisor toggle: redis mirror failed for %s", advisor_key)

    def is_model_available(self, advisor_key: str) -> bool:
        """Public: is the advisor's ML artifact present + loadable right now."""
        return self._model_available(advisor_key)

    def _model_available(self, advisor_key: str) -> bool:
        probe = self._availability.get(advisor_key)
        try:
            return bool(probe()) if probe else False
        except Exception:
            return False

    def _build_item(self, advisor_key: str, state: str) -> AdvisorToggleItemDTO:
        meta = ADVISOR_REGISTRY[advisor_key]
        model_available = self._model_available(advisor_key)
        serving, status = self._derive_status(state, model_available)

        raw_metrics = load_model_metrics(meta["metrics_stem"])
        metrics: dict = {}
        summary_parts: list[str] = []
        for key, label in meta["metric_fields"]:
            if key in raw_metrics and isinstance(raw_metrics[key], (int, float)):
                value = round(float(raw_metrics[key]), 2)
                metrics[key] = value
                summary_parts.append(f"{label} {value}")

        return AdvisorToggleItemDTO(
            advisor_key=advisor_key,
            name=meta["name"],
            description=meta["description"],
            state=state,
            state_label=STATE_LABELS.get(state, state),
            model_version=raw_metrics.get("model_version"),
            model_available=model_available,
            serving=serving,
            status=status,
            metrics=metrics,
            metrics_summary=" · ".join(summary_parts),
        )

    @staticmethod
    def _derive_status(state: str, model_available: bool) -> tuple[str, str]:
        if state == AdvisorState.OFF.value:
            return SERVING_OFF, STATUS_OFF
        if state == AdvisorState.FORCE_RULES.value:
            return SERVING_RULES, STATUS_DEGRADED
        # ON — ML if the artifact is loadable, else degraded to rules
        if model_available:
            return SERVING_ML, STATUS_LIVE
        return SERVING_RULES, STATUS_DEGRADED

    @staticmethod
    def _actor_uuid(current_user: dict):
        sub = current_user.get("sub")
        return uuid.UUID(sub) if sub else None
