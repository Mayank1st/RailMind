from typing import Optional

from pydantic import Field

from app.domain.admin.constants.admin_rate_limits import RateLimitScope
from app.schemas.base import BaseDTO


# -- CreateRateLimitRequest ("Add rate limit" drawer) ------------
class CreateRateLimitRequestDTO(BaseDTO):
    endpoint: str = Field(min_length=1, max_length=120)  # limiter scope key
    scope_type: RateLimitScope
    window_seconds: int = Field(ge=1, le=86_400)  # 1s … 24h
    limit: int = Field(ge=1, le=1_000_000)


# -- UpdateRateLimitRequest ("Edit" drawer, partial) -------------
class UpdateRateLimitRequestDTO(BaseDTO):
    endpoint: Optional[str] = Field(default=None, min_length=1, max_length=120)
    scope_type: Optional[RateLimitScope] = None
    window_seconds: Optional[int] = Field(default=None, ge=1, le=86_400)
    limit: Optional[int] = Field(default=None, ge=1, le=1_000_000)
