import uuid
from typing import Optional

from fastapi_pagination import Params
from fastapi_pagination.bases import AbstractPage
from fastapi_pagination.ext.sqlalchemy import apaginate
from sqlalchemy import select
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import NullPool

from app.db.base import DATABASE_URL, DB_SCHEMA
from app.db.models.admin_audit_log import AdminAuditLogs
from app.domain.admin.dto.admin_audit_logs_filter_dto import AdminAuditLogFilterDTO
from app.domain.admin.dto.admin_audit_logs_response_dto import AdminAuditLogResponseDTO
from app.utils.logger import logger

_event_engine = create_async_engine(
    DATABASE_URL,
    poolclass=NullPool,
    connect_args={"server_settings": {"search_path": f'"{DB_SCHEMA}"'}},
)
_event_session = async_sessionmaker(bind=_event_engine, expire_on_commit=False)


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

    async def record_event(
        self,
        *,
        actor_id: Optional[str],
        actor_username: Optional[str],
        action: str,
        target_type: str,
        target_id: Optional[str] = None,
        before: Optional[dict] = None,
        after: Optional[dict] = None,
        reason: Optional[str] = None,
        ip: Optional[str] = None,
    ) -> None:
        """Best-effort audit write on its OWN transaction. Use for events that
        must persist even when the request rolls back (failed logins) or that
        aren't tied to a mutating request txn (login/logout). NEVER raises —
        auditing an auth event must not turn it into a crash."""
        try:
            async with _event_session() as db:
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
                await db.commit()
        except Exception:
            logger.exception("admin_audit: could not record event action=%s", action)

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
