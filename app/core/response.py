# app/core/response.py

from typing import Any, Generic, Optional, TypeVar

from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

T = TypeVar("T")


# ─── Error Detail ─────────────────────────────────────────────────────────────


class ErrorDetail(BaseModel):
    code: str  # RM-{DOMAIN}-{NUMBER} e.g. "RM-AUTH-001"
    field: Optional[str] = None  # populated for validation errors
    message: str


# ─── Core Envelope ────────────────────────────────────────────────────────────


class APIResponse(BaseModel, Generic[T]):
    success: bool
    message: str
    data: Optional[T] = None
    errors: Optional[list[ErrorDetail]] = None
    meta: Optional[dict] = None  # caller-controlled: pagination, ai_confidence, etc.


# ─── Success Factories ────────────────────────────────────────────────────────


def ok(
    data: Any = None,
    *,
    message: str = "Success",
    meta: Optional[dict] = None,
) -> APIResponse:
    return APIResponse(success=True, message=message, data=data, meta=meta)


def created(data: Any = None, *, message: str = "Created successfully") -> APIResponse:
    return APIResponse(success=True, message=message, data=data)


# ─── Error Factories ──────────────────────────────────────────────────────────


def error(
    message: str,
    *,
    code: str,
    field: Optional[str] = None,
) -> APIResponse:
    return APIResponse(
        success=False,
        message=message,
        errors=[ErrorDetail(code=code, field=field, message=message)],
    )


def validation_error(pydantic_errors: list[dict]) -> APIResponse:
    """For use in the 422 exception handler."""
    details = [
        ErrorDetail(
            code="RM-VAL-001",
            field=".".join(str(loc) for loc in e.get("loc", [])[1:]),
            message=e.get("msg", "Validation error"),
        )
        for e in pydantic_errors
    ]
    return APIResponse(success=False, message="Validation failed", errors=details)


# ─── JSONResponse helper (for exception handlers only) ───────────────────────


def json_error(message: str, *, status_code: int, code: str) -> JSONResponse:
    body = error(message, code=code)
    return JSONResponse(status_code=status_code, content=jsonable_encoder(body))
