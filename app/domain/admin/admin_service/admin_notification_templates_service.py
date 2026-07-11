import re
import uuid
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import RailMindException
from app.db.models.notification_template import NotificationTemplates
from app.domain.admin.admin_service.admin_audit_service import AdminAuditService
from app.domain.admin.constants.admin_audit import AuditAction, AuditTargetType
from app.domain.admin.constants.admin_notification_templates import (
    CHANNEL_LABELS,
    ERR_TEMPLATE_DUPLICATE_KEY,
    ERR_TEMPLATE_NOT_FOUND,
    PREVIEW_SAMPLE_DATA,
    PREVIEW_TEXT_MAX,
    STATUS_LABELS,
    NotificationChannel,
)
from app.domain.admin.dto.admin_notification_templates_request_dto import (
    CreateNotificationTemplateRequestDTO,
    PreviewNotificationTemplateRequestDTO,
    UpdateNotificationTemplateRequestDTO,
)
from app.domain.admin.dto.admin_notification_templates_response_dto import (
    NotificationTemplateItemDTO,
    NotificationTemplatePreviewDTO,
)
from app.utils.logger import logger

_VAR_RE = re.compile(r"\{\{\s*(\w+)\s*\}\}")
_AUDIT_SNAPSHOT_FIELDS = ("template_key", "channel", "subject", "body", "status")

audit_service = AdminAuditService()


class AdminNotificationTemplatesService:
    """Config → Notification Templates CRUD + live {{variable}} preview, audited.
    Editable store only — the notification send path is untouched (a follow-up)."""

    # ── Read ────────────────────────────────────────────────────────────────

    async def list_templates(
        self, db: AsyncSession
    ) -> list[NotificationTemplateItemDTO]:
        rows = (
            (
                await db.execute(
                    select(NotificationTemplates).order_by(
                        NotificationTemplates.updated_at.desc()
                    )
                )
            )
            .scalars()
            .all()
        )
        return [self._serialize(row) for row in rows]

    def preview(
        self, payload: PreviewNotificationTemplateRequestDTO
    ) -> NotificationTemplatePreviewDTO:
        is_email = payload.channel == NotificationChannel.EMAIL
        return NotificationTemplatePreviewDTO(
            subject_rendered=(self._render(payload.subject) if is_email else None),
            body_rendered=self._render(payload.body),
        )

    # ── Actions (audited, super-admin) ──────────────────────────────────────

    async def create_template(
        self,
        payload: CreateNotificationTemplateRequestDTO,
        current_user: dict,
        ip: Optional[str],
        db: AsyncSession,
    ) -> NotificationTemplateItemDTO:
        await self._ensure_key_free(db, payload.template_key, exclude_id=None)
        row = NotificationTemplates(
            template_key=payload.template_key,
            channel=payload.channel.value,
            subject=payload.subject,
            body=payload.body,
            status=payload.status.value,
            created_by=self._actor_uuid(current_user),
        )
        db.add(row)
        await db.flush()
        await self._audit(
            db,
            current_user,
            AuditAction.TEMPLATE_CREATED.value,
            row.id,
            before=None,
            after=self._snapshot(row),
            ip=ip,
        )
        await db.flush()
        logger.info("Notification template created key=%s", row.template_key)
        return self._serialize(row)

    async def update_template(
        self,
        template_id: uuid.UUID,
        payload: UpdateNotificationTemplateRequestDTO,
        current_user: dict,
        ip: Optional[str],
        db: AsyncSession,
    ) -> NotificationTemplateItemDTO:
        row = await self._load(template_id, db)
        changes = payload.model_dump(exclude_none=True)
        if not changes:
            return self._serialize(row)

        if "template_key" in changes and changes["template_key"] != row.template_key:
            await self._ensure_key_free(db, changes["template_key"], exclude_id=row.id)

        before = self._snapshot(row)
        for field, value in changes.items():
            setattr(row, field, value.value if hasattr(value, "value") else value)
        await db.flush()
        await self._audit(
            db,
            current_user,
            AuditAction.TEMPLATE_UPDATED.value,
            row.id,
            before=before,
            after=self._snapshot(row),
            ip=ip,
        )
        await db.flush()
        logger.info("Notification template updated key=%s", row.template_key)
        return self._serialize(row)

    async def delete_template(
        self,
        template_id: uuid.UUID,
        current_user: dict,
        ip: Optional[str],
        db: AsyncSession,
    ) -> dict:
        row = await self._load(template_id, db)
        snapshot = self._snapshot(row)
        await self._audit(
            db,
            current_user,
            AuditAction.TEMPLATE_DELETED.value,
            row.id,
            before=snapshot,
            after=None,
            ip=ip,
        )
        await db.delete(row)
        await db.flush()
        logger.info("Notification template deleted key=%s", snapshot["template_key"])
        return {"template_id": str(template_id), "deleted": True}

    # ── Helpers ─────────────────────────────────────────────────────────────

    @staticmethod
    def _render(text: Optional[str]) -> str:
        """Substitute {{var}} with preview sample values; unknown vars left as-is."""
        if not text:
            return ""
        return _VAR_RE.sub(
            lambda m: str(PREVIEW_SAMPLE_DATA.get(m.group(1), m.group(0))), text
        )

    async def _ensure_key_free(
        self, db: AsyncSession, template_key: str, exclude_id: Optional[uuid.UUID]
    ) -> None:
        query = select(NotificationTemplates.id).where(
            NotificationTemplates.template_key == template_key
        )
        if exclude_id is not None:
            query = query.where(NotificationTemplates.id != exclude_id)
        if (await db.execute(query)).first() is not None:
            raise RailMindException(
                code=ERR_TEMPLATE_DUPLICATE_KEY,
                message=f"A template with key '{template_key}' already exists.",
                status_code=409,
            )

    async def _load(
        self, template_id: uuid.UUID, db: AsyncSession
    ) -> NotificationTemplates:
        row = (
            await db.execute(
                select(NotificationTemplates).where(
                    NotificationTemplates.id == template_id
                )
            )
        ).scalar_one_or_none()
        if row is None:
            raise RailMindException(
                code=ERR_TEMPLATE_NOT_FOUND,
                message="Notification template not found.",
                status_code=404,
            )
        return row

    @staticmethod
    def _actor_uuid(current_user: dict):
        sub = current_user.get("sub")
        return uuid.UUID(sub) if sub else None

    @staticmethod
    def _snapshot(row: NotificationTemplates) -> dict:
        return {f: getattr(row, f) for f in _AUDIT_SNAPSHOT_FIELDS}

    async def _audit(
        self, db, current_user, action, target_id, *, before, after, ip
    ) -> None:
        await audit_service.record(
            db,
            actor_id=current_user.get("sub"),
            actor_username=current_user.get("username"),
            action=action,
            target_type=AuditTargetType.TEMPLATE.value,
            target_id=target_id,
            before=before,
            after=after,
            ip=ip,
        )

    def _serialize(self, row: NotificationTemplates) -> NotificationTemplateItemDTO:
        if row.channel == NotificationChannel.EMAIL.value:
            preview_text = (row.subject or "")[:PREVIEW_TEXT_MAX]
        else:
            preview_text = (row.body or "")[:PREVIEW_TEXT_MAX]
        return NotificationTemplateItemDTO(
            template_id=str(row.id),
            template_key=row.template_key,
            channel=row.channel,
            channel_label=CHANNEL_LABELS.get(row.channel, row.channel),
            subject=row.subject,
            body=row.body,
            preview_text=preview_text,
            status=row.status,
            status_label=STATUS_LABELS.get(row.status, row.status),
            last_edited=row.updated_at,
        )
