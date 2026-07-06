import traceback
import uuid
from typing import Optional

from fastapi import Request
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.core.security import decode_access_token
from app.db.base import DATABASE_URL, DB_SCHEMA
from app.db.models.error_log import ErrorLogs
from app.utils.logger import logger

# Dedicated NullPool engine: exception handlers can fire when the request's own
# DB session is already broken (esp. DatabaseError), so error-log writes must go
# through a fresh, independent connection. NullPool caches nothing → safe.
_engine = create_async_engine(
    DATABASE_URL,
    poolclass=NullPool,
    connect_args={"server_settings": {"search_path": f'"{DB_SCHEMA}"'}},
)
_session = async_sessionmaker(bind=_engine, expire_on_commit=False)

SEVERITY_ERROR = "ERROR"  # 5xx — server-side
SEVERITY_WARNING = "WARNING"  # 4xx — client/business

# High-frequency, low-signal codes that fire on normal logged-out / expired
# browsing — persisting them would flood the table. Tune this list as needed.
EXCLUDED_ERROR_CODES = frozenset({"RM-AUTH-019", "RM-AUTH-002"})

MESSAGE_MAX_LEN = 4000
TRACE_MAX_LEN = 8000


def _severity(status_code: int) -> str:
    return SEVERITY_ERROR if status_code >= 500 else SEVERITY_WARNING


def _domain(code: str) -> Optional[str]:
    # RM-BKG-001 -> BKG ; RM-ADMIN-AUTH-001 -> ADMIN
    parts = code.split("-")
    return parts[1] if len(parts) >= 2 and parts[0] == "RM" else None


def _client_ip(request: Request) -> Optional[str]:
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else None


def _actor_id(request: Request) -> Optional[str]:
    token = request.cookies.get("access_token")
    if not token:
        return None
    try:
        return decode_access_token(token).get("sub")
    except Exception:
        return None  # missing/expired token is often *why* there's an error


async def record_from_request(
    request: Request,
    code: str,
    message: str,
    status_code: int,
    exc: Optional[BaseException] = None,
) -> None:
    """Persist one error, best-effort. NEVER raises — error logging must not turn
    a handled error into a crash. Skips excluded / non-RM codes."""
    if code in EXCLUDED_ERROR_CODES:
        return
    try:
        trace = None
        if status_code >= 500 and exc is not None:
            trace = "".join(
                traceback.format_exception(type(exc), exc, exc.__traceback__)
            )[:TRACE_MAX_LEN]

        actor = _actor_id(request)
        async with _session() as db:
            db.add(
                ErrorLogs(
                    code=code,
                    domain=_domain(code),
                    severity=_severity(status_code),
                    status_code=status_code,
                    message=(message or "")[:MESSAGE_MAX_LEN],
                    method=request.method,
                    path=request.url.path,
                    exception_type=type(exc).__name__ if exc else None,
                    user_id=uuid.UUID(actor) if actor else None,
                    ip=_client_ip(request),
                    trace=trace,
                )
            )
            await db.commit()
    except Exception:
        logger.exception("error_log: could not record code=%s", code)
