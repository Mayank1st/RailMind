from sqlalchemy import String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import BaseModel


class AdminAuditLogs(BaseModel):
    """Immutable trail of every sensitive admin action (who / what / when).

    Written in the same transaction as the action it records, so an action can
    never persist without its audit entry. Deliberately FK-free and
    denormalized (actor_username, before/after snapshots) — a log must survive
    and read correctly even if its subject is later changed or deleted.
    """

    __tablename__ = "admin_audit_logs"

    actor_user_id: Mapped[UUID | None] = mapped_column(
        UUID(as_uuid=True), nullable=True, index=True
    )
    actor_username: Mapped[str | None] = mapped_column(String(50), nullable=True)
    action: Mapped[str] = mapped_column(String(60), nullable=False, index=True)
    target_type: Mapped[str] = mapped_column(String(30), nullable=False, index=True)
    target_id: Mapped[str | None] = mapped_column(
        String(100), nullable=True, index=True
    )
    before: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    after: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    reason: Mapped[str | None] = mapped_column(String(500), nullable=True)
    ip: Mapped[str | None] = mapped_column(String(64), nullable=True)

    def __repr__(self) -> str:
        return (
            f"<AdminAuditLogs id={self.id} action={self.action} "
            f"target={self.target_type}:{self.target_id}>"
        )
