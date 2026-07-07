import uuid
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import update
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.config import settings
from app.db.base import DATABASE_URL, DB_SCHEMA
from app.db.models.email_log import EmailLogs
from app.domain.admin.constants.admin import EmailLogStatus
from app.utils.logger import logger

# Emails send across three event loops — the uvicorn request loop, the Celery
# worker loop, and the throwaway loop the OTP thread spins up per send. A pooled
# connection bound to one loop and reused on another raises "Future attached to a
# different loop". A NullPool engine caches nothing, so every write opens a fresh
# asyncpg connection on the *current* loop and disposes it — safe everywhere.
# Volume is low (transactional emails only), so per-write connections are fine.
_engine = create_async_engine(
    DATABASE_URL,
    poolclass=NullPool,
    connect_args={"server_settings": {"search_path": f'"{DB_SCHEMA}"'}},
)
_session = async_sessionmaker(bind=_engine, expire_on_commit=False)

ERROR_MAX_LEN = 2000


def _as_uuid(value: Optional[str]) -> Optional[uuid.UUID]:
    return uuid.UUID(value) if value else None


async def record_email_queued(
    to_email: str,
    subject: str,
    template: Optional[str],
    category: str,
    context: Optional[dict],
    linked_type: Optional[str],
    linked_label: Optional[str],
    user_id: Optional[str],
    booking_id: Optional[str],
) -> Optional[str]:
    """Insert a QUEUED row and return its id (or None). Best-effort: email-log
    writes must NEVER break the actual send, so all failures are swallowed."""
    try:
        async with _session() as db:
            row = EmailLogs(
                to_email=to_email,
                subject=subject,
                template=template,
                category=category,
                status=EmailLogStatus.QUEUED.value,
                provider=settings.EMAIL_SMTP_HOST,
                context=context,
                linked_type=linked_type,
                linked_label=linked_label,
                user_id=_as_uuid(user_id),
                booking_id=_as_uuid(booking_id),
                queued_at=datetime.now(timezone.utc),
            )
            db.add(row)
            await db.commit()
            return str(row.id)
    except Exception:
        logger.exception("email_log: could not record QUEUED to=%s", to_email)
        return None


async def mark_email_sent(log_id: Optional[str]) -> None:
    if not log_id:
        return
    try:
        async with _session() as db:
            await db.execute(
                update(EmailLogs)
                .where(EmailLogs.id == log_id)
                .values(
                    status=EmailLogStatus.SENT.value,
                    sent_at=datetime.now(timezone.utc),
                )
            )
            await db.commit()
    except Exception:
        logger.exception("email_log: could not mark SENT id=%s", log_id)


async def mark_email_failed(log_id: Optional[str], error: str) -> None:
    if not log_id:
        return
    try:
        async with _session() as db:
            await db.execute(
                update(EmailLogs)
                .where(EmailLogs.id == log_id)
                .values(
                    status=EmailLogStatus.FAILED.value,
                    error=error[:ERROR_MAX_LEN],
                    failed_at=datetime.now(timezone.utc),
                )
            )
            await db.commit()
    except Exception:
        logger.exception("email_log: could not mark FAILED id=%s", log_id)
