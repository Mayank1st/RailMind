import uuid
from typing import Optional

from fastapi_pagination import Params
from fastapi_pagination.bases import AbstractPage
from fastapi_pagination.ext.sqlalchemy import apaginate
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.admin_audit_log import AdminAuditLogs
from app.domain.admin.dto.admin_audit_logs_filter_dto import AdminAuditLogFilterDTO
from app.domain.admin.dto.admin_audit_logs_response_dto import AdminAuditLogResponseDTO


class AdminAuditService:
    """Writes AND reads the audit trail. On write, always call with the request's
    `db` session and DO NOT commit here — the row is flushed into the caller's
    transaction so the action and its audit entry commit together (or roll back
    together). Reads power the Audit Log screen."""

    async def record(
        self,
        db: AsyncSession,
        *,
        actor_id: Optional[str],
        actor_username: Optional[str],
        action: str,
        target_type: str,
        target_id: Optional[str],
        before: Optional[dict] = None,
        after: Optional[dict] = None,
        reason: Optional[str] = None,
        ip: Optional[str] = None,
    ) -> None:
        db.add(
            AdminAuditLogs(
                actor_user_id=uuid.UUID(actor_id) if actor_id else None,
                actor_username=actor_username,
                action=action,
                target_type=target_type,
                target_id=str(target_id) if target_id is not None else None,
                before=before,
                after=after,
                reason=reason,
                ip=ip,
            )
        )
        await db.flush()

    # ── Read (Audit Log screen) ─────────────────────────────────────────────

    async def list_audit_logs(
        self,
        db: AsyncSession,
        audit_filter: AdminAuditLogFilterDTO,
        params: Params,
    ) -> AbstractPage:
        query = select(AdminAuditLogs)
        query = audit_filter.filter(query)
        query = audit_filter.sort(query)
        return await apaginate(
            db,
            query,
            params,
            transformer=lambda rows: [self._serialize(row) for row in rows],
        )

    @staticmethod
    def _serialize(row: AdminAuditLogs) -> AdminAuditLogResponseDTO:
        return AdminAuditLogResponseDTO(
            audit_log_id=str(row.id),
            actor_user_id=str(row.actor_user_id) if row.actor_user_id else None,
            actor_username=row.actor_username,
            action=row.action,
            target_type=row.target_type,
            target_id=row.target_id,
            before=row.before,
            after=row.after,
            reason=row.reason,
            ip=row.ip,
            created_at=row.created_at,
        )
