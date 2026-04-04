from collections.abc import AsyncGenerator

from fastapi import Cookie, Depends, Header
from jose import JWTError
from redis.asyncio import Redis

from app.config import settings
from app.core.exceptions import RailMindException
from app.core.security import decode_access_token
from app.db.session import get_db  # noqa: F401  re-exported for convenience

__all__ = ["get_db", "get_redis", "get_current_user", "get_current_user_with_csrf"]


# ─── Redis ────────────────────────────────────────────────────────────────────

async def get_redis() -> AsyncGenerator[Redis, None]:
    redis = Redis.from_url(
        settings.REDIS_URL,
        encoding="utf-8",
        decode_responses=True,  
    )
    try:
        yield redis
    finally:
        await redis.aclose()


# ─── Current User ─────────────────────────────────────────────────────────────

async def get_current_user(
    access_token: str = Cookie(None, alias="access_token"),
    redis: Redis = Depends(get_redis),
) -> dict:
    # ── 1. Token missing ──────────────────────────────────────────────────────
    if not access_token:
        raise RailMindException(
            code="RM-AUTH-001",
            message="Not authenticated. Please login",
            status_code=401,
        )

    # ── 2. Decode and verify JWT signature + expiry ───────────────────────────
    try:
        payload = decode_access_token(access_token)
    except JWTError:
        raise RailMindException(
            code="RM-AUTH-002",
            message="Invalid or expired token. Please login again",
            status_code=401,
        )

    # ── 3. Check token is blacklisted (user already logged out) ───────────────
    jti = payload.get("jti")
    if jti and await redis.exists(f"blacklist:{jti}"):
        raise RailMindException(
            code="RM-AUTH-002",
            message="Token has been revoked. Please login again",
            status_code=401,
        )
    
    return payload


# ─── Current User + CSRF ──────────────────────────────────────────────────────

async def get_current_user_with_csrf(
    access_token: str = Cookie(None, alias="access_token"),
    csrf_cookie: str = Cookie(None, alias="csrf_token"),
    csrf_header: str = Header(None, alias="X-CSRF-Token"),
    redis: Redis = Depends(get_redis),
) -> dict:
    # ── 1. Validate JWT first ─────────────────────────────────────────────────
    user = await get_current_user(access_token, redis)

    # ── 2. CSRF cookie must exist ─────────────────────────────────────────────
    if not csrf_cookie:
        raise RailMindException(
            code="RM-AUTH-010",
            message="CSRF token missing",
            status_code=403,
        )

    # ── 3. CSRF header must exist ─────────────────────────────────────────────
    if not csrf_header:
        raise RailMindException(
            code="RM-AUTH-010",
            message="X-CSRF-Token header missing",
            status_code=403,
        )

    # ── 4. Both must match ────────────────────────────────────────────────────
    if csrf_cookie != csrf_header:
        raise RailMindException(
            code="RM-AUTH-010",
            message="CSRF validation failed",
            status_code=403,
        )

    return user