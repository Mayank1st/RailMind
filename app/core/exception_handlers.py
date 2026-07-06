from fastapi import Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy.exc import InterfaceError, OperationalError, SQLAlchemyError

from app.config import settings
from app.core.error_log_writer import record_from_request
from app.core.exceptions import DatabaseError, RailMindException
from app.core.response import json_error, validation_error
from app.utils.logger import logger


def _ctx(request: Request) -> str:
    """Compact request descriptor for log lines, e.g. 'POST /api/v1/auth/login'."""
    return f"{request.method} {request.url.path}"


async def railmind_exception_handler(
    request: Request, exc: RailMindException
) -> JSONResponse:
    log_line = "%s -> %s (%s): %s"
    if exc.status_code >= 500:
        logger.error(
            log_line,
            _ctx(request),
            exc.code,
            exc.status_code,
            exc.message,
            exc_info=exc,
        )
    else:
        logger.info(log_line, _ctx(request), exc.code, exc.status_code, exc.message)
    await record_from_request(request, exc.code, exc.message, exc.status_code, exc=exc)
    return json_error(exc.message, status_code=exc.status_code, code=exc.code)


async def validation_exception_handler(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    logger.info("%s -> 422 validation failed: %s", _ctx(request), exc.errors())
    body = validation_error(exc.errors())
    return JSONResponse(status_code=422, content=jsonable_encoder(body))


async def database_exception_handler(
    request: Request, exc: SQLAlchemyError
) -> JSONResponse:
    logger.error(
        "%s -> database error [%s]: %s",
        _ctx(request),
        type(exc).__name__,
        exc,
        exc_info=exc,
    )

    # Connection-level failures are usually transient -> tell the caller to retry.
    if isinstance(exc, (OperationalError, InterfaceError)):
        status_code = 503
        message = "Service temporarily unavailable. Please try again later."
    else:
        status_code = 500
        message = DatabaseError.message

    await record_from_request(
        request, DatabaseError.error_code, message, status_code, exc=exc
    )

    # Surface the real cause in non-prod so developers don't have to dig in logs.
    if settings.DEBUG:
        message = f"{message} [{type(exc).__name__}: {exc}]"

    return json_error(message, status_code=status_code, code=DatabaseError.error_code)


async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    logger.error(
        "%s -> unhandled %s: %s",
        _ctx(request),
        type(exc).__name__,
        exc,
        exc_info=exc,
    )
    await record_from_request(
        request, "RM-GEN-001", "An unexpected error occurred", 500, exc=exc
    )
    return json_error(
        "An unexpected error occurred", status_code=500, code="RM-GEN-001"
    )
