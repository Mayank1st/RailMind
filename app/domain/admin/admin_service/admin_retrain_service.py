import uuid
from datetime import datetime, timezone
from typing import Optional

from redis.asyncio import Redis
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import RailMindException
from app.db.models.retrain_candidate import RetrainCandidates
from app.domain.admin.admin_service.admin_audit_service import AdminAuditService
from app.domain.admin.admin_service.admin_model_versions_service import (
    AdminModelVersionsService,
)
from app.domain.admin.constants.admin_ai_control import ADVISOR_REGISTRY
from app.domain.admin.constants.admin_audit import AuditAction, AuditTargetType
from app.domain.admin.constants.admin_retrain import (
    ALGO_ABBR,
    CANDIDATE_FAMILY,
    ERR_RETRAIN_ADVISOR_NOT_FOUND,
    ERR_RETRAIN_ALREADY_PROMOTED,
    ERR_RETRAIN_GATE_NOT_PASSED,
    ERR_RETRAIN_NOT_FOUND,
    ERR_RETRAIN_NOT_TRAINED,
    GATE_STATUS_FAILED,
    GATE_STATUS_PASSED,
    GATE_STATUS_PENDING,
    TRAINING_WINDOW_LABELS,
    RetrainStatus,
)
from app.domain.admin.dto.admin_retrain_request_dto import TriggerRetrainRequestDTO
from app.domain.admin.dto.admin_retrain_response_dto import (
    RetrainCandidateItemDTO,
    RetrainReportDTO,
)
from app.utils.logger import logger

audit_service = AdminAuditService()
model_versions_service = AdminModelVersionsService()


class AdminRetrainService:
    """AI Control → Retrain. The admin panel GOVERNS retraining: trigger a request,
    review the gate, promote a passing candidate to the active model version.

    Training executes in a DECOUPLED runner (offline scripts/phase-2 or a dedicated
    training worker) which fills a candidate's result via `register_result`. It is
    never run inline here — that would block time-critical Celery work and its
    artifacts don't share across a multi-node deploy.
    """

    # ── Trigger (super-admin) ───────────────────────────────────────────────

    async def trigger_retrain(
        self,
        payload: TriggerRetrainRequestDTO,
        current_user: dict,
        ip: Optional[str],
        db: AsyncSession,
    ) -> RetrainCandidateItemDTO:
        advisor_key = payload.advisor_key.value
        label = await self._next_label(db, advisor_key, payload.algorithm.value)
        row = RetrainCandidates(
            advisor_key=advisor_key,
            candidate_label=label,
            status=RetrainStatus.QUEUED.value,
            algorithm=payload.algorithm.value,
            training_window=payload.training_window.value,
            validation_split=payload.validation_split,
            gate_min_precision=payload.gate_min_precision,
            gate_min_recall=payload.gate_min_recall,
            created_by=self._actor_uuid(current_user),
        )
        db.add(row)
        await db.flush()
        await self._audit(
            db,
            current_user,
            AuditAction.RETRAIN_TRIGGERED.value,
            advisor_key,
            after={"candidate": label, "algorithm": payload.algorithm.value},
            ip=ip,
        )
        await db.flush()
        # NOTE: a decoupled training runner picks up QUEUED candidates and calls
        # register_result. We intentionally do NOT train in this process.
        logger.info("Retrain queued %s for %s", label, advisor_key)
        return self._serialize_item(row)

    # ── Read ────────────────────────────────────────────────────────────────

    async def list_candidates(self, db: AsyncSession) -> list[RetrainCandidateItemDTO]:
        rows = (
            (
                await db.execute(
                    select(RetrainCandidates).order_by(
                        RetrainCandidates.created_at.desc()
                    )
                )
            )
            .scalars()
            .all()
        )
        return [self._serialize_item(r) for r in rows]

    async def get_report(
        self, db: AsyncSession, candidate_id: uuid.UUID
    ) -> RetrainReportDTO:
        row = await self._load(candidate_id, db)
        return self._serialize_report(row)

    # ── Result registration (called by the DECOUPLED training runner) ────────

    async def register_result(
        self,
        db: AsyncSession,
        candidate_id: uuid.UUID,
        *,
        precision: float,
        recall: float,
        confusion: Optional[dict] = None,
        feature_importance: Optional[list] = None,
        rows_trained: Optional[int] = None,
        duration_seconds: Optional[int] = None,
        artifact_stem: Optional[str] = None,
        baseline_precision: Optional[float] = None,
        baseline_recall: Optional[float] = None,
    ) -> RetrainReportDTO:
        row = await self._load(candidate_id, db)
        row.precision = precision
        row.recall = recall
        row.gate_passed = (
            precision >= row.gate_min_precision and recall >= row.gate_min_recall
        )
        row.confusion = confusion
        row.feature_importance = feature_importance
        row.rows_trained = rows_trained
        row.duration_seconds = duration_seconds
        row.artifact_stem = artifact_stem
        row.baseline_precision = baseline_precision
        row.baseline_recall = baseline_recall
        row.trained_at = datetime.now(timezone.utc)
        row.status = RetrainStatus.TRAINED.value
        await db.flush()
        logger.info(
            "Retrain result registered %s gate=%s", row.candidate_label, row.gate_passed
        )
        return self._serialize_report(row)

    # ── Promote (super-admin, gate-enforced) ────────────────────────────────

    async def promote(
        self,
        candidate_id: uuid.UUID,
        reason: str,
        current_user: dict,
        ip: Optional[str],
        db: AsyncSession,
        redis: Redis,
    ) -> RetrainReportDTO:
        row = await self._load(candidate_id, db)
        if row.status == RetrainStatus.PROMOTED.value:
            raise RailMindException(
                code=ERR_RETRAIN_ALREADY_PROMOTED,
                message="This candidate is already promoted.",
                status_code=409,
            )
        if row.status != RetrainStatus.TRAINED.value:
            raise RailMindException(
                code=ERR_RETRAIN_NOT_TRAINED,
                message="Candidate has no training result yet.",
                status_code=400,
            )
        if not row.gate_passed:
            raise RailMindException(
                code=ERR_RETRAIN_GATE_NOT_PASSED,
                message="Candidate failed the gate and cannot be promoted.",
                status_code=400,
            )

        await model_versions_service.register_promotion(
            advisor_key=row.advisor_key,
            version_label=row.candidate_label,
            artifact_stem=row.artifact_stem,
            metrics={"precision": row.precision, "recall": row.recall},
            trained_at=row.trained_at.date() if row.trained_at else None,
            current_user=current_user,
            db=db,
            redis=redis,
        )

        row.status = RetrainStatus.PROMOTED.value
        row.promoted_at = datetime.now(timezone.utc)
        row.promote_reason = reason
        await db.flush()
        await self._audit(
            db,
            current_user,
            AuditAction.MODEL_PROMOTED.value,
            row.advisor_key,
            after={
                "candidate": row.candidate_label,
                "precision": row.precision,
                "recall": row.recall,
                "reason": reason,
            },
            ip=ip,
        )
        await db.flush()
        logger.info("Candidate promoted %s -> active", row.candidate_label)
        return self._serialize_report(row)

    # ── Helpers ─────────────────────────────────────────────────────────────

    async def _next_label(
        self, db: AsyncSession, advisor_key: str, algorithm: str
    ) -> str:
        family = CANDIDATE_FAMILY.get(advisor_key, advisor_key)
        abbr = ALGO_ABBR.get(algorithm, "m")
        seq = (
            await db.scalar(
                select(func.count())
                .select_from(RetrainCandidates)
                .where(RetrainCandidates.advisor_key == advisor_key)
            )
        ) or 0
        return f"{family}-{abbr}-rc-{seq + 1}"

    async def _load(
        self, candidate_id: uuid.UUID, db: AsyncSession
    ) -> RetrainCandidates:
        row = (
            await db.execute(
                select(RetrainCandidates).where(RetrainCandidates.id == candidate_id)
            )
        ).scalar_one_or_none()
        if row is None:
            raise RailMindException(
                code=ERR_RETRAIN_NOT_FOUND,
                message="Retrain candidate not found.",
                status_code=404,
            )
        return row

    @staticmethod
    def _ensure_advisor(advisor_key: str) -> None:
        if advisor_key not in ADVISOR_REGISTRY:
            raise RailMindException(
                code=ERR_RETRAIN_ADVISOR_NOT_FOUND,
                message=f"Unknown advisor '{advisor_key}'.",
                status_code=404,
            )

    @staticmethod
    def _gate_status(row: RetrainCandidates) -> str:
        if row.status in (RetrainStatus.QUEUED.value, RetrainStatus.RUNNING.value):
            return GATE_STATUS_PENDING
        return GATE_STATUS_PASSED if row.gate_passed else GATE_STATUS_FAILED

    @staticmethod
    def _can_promote(row: RetrainCandidates) -> bool:
        return (
            row.status == RetrainStatus.TRAINED.value
            and bool(row.gate_passed)
            and row.promoted_at is None
        )

    def _serialize_item(self, row: RetrainCandidates) -> RetrainCandidateItemDTO:
        return RetrainCandidateItemDTO(
            candidate_id=str(row.id),
            candidate_label=row.candidate_label,
            advisor_key=row.advisor_key,
            advisor_name=ADVISOR_REGISTRY.get(row.advisor_key, {}).get(
                "name", row.advisor_key
            ),
            precision=row.precision,
            recall=row.recall,
            gate_passed=row.gate_passed,
            gate_status=self._gate_status(row),
            status=row.status,
            trained_at=row.trained_at,
            can_promote=self._can_promote(row),
        )

    def _serialize_report(self, row: RetrainCandidates) -> RetrainReportDTO:
        p_delta = (
            round(row.precision - row.baseline_precision, 4)
            if row.precision is not None and row.baseline_precision is not None
            else None
        )
        r_delta = (
            round(row.recall - row.baseline_recall, 4)
            if row.recall is not None and row.baseline_recall is not None
            else None
        )
        return RetrainReportDTO(
            candidate_id=str(row.id),
            candidate_label=row.candidate_label,
            advisor_key=row.advisor_key,
            advisor_name=ADVISOR_REGISTRY.get(row.advisor_key, {}).get(
                "name", row.advisor_key
            ),
            status=row.status,
            gate_status=self._gate_status(row),
            gate_passed=row.gate_passed,
            algorithm=row.algorithm,
            training_window=TRAINING_WINDOW_LABELS.get(
                row.training_window, row.training_window
            ),
            validation_split=row.validation_split,
            precision=row.precision,
            recall=row.recall,
            gate_min_precision=row.gate_min_precision,
            gate_min_recall=row.gate_min_recall,
            precision_vs_baseline=p_delta,
            recall_vs_baseline=r_delta,
            confusion=row.confusion,
            feature_importance=row.feature_importance,
            rows_trained=row.rows_trained,
            duration_seconds=row.duration_seconds,
            trained_at=row.trained_at,
            error=row.error,
            promoted_at=row.promoted_at,
            promote_reason=row.promote_reason,
            can_promote=self._can_promote(row),
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
