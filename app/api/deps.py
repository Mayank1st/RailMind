from collections.abc import AsyncGenerator
from typing import Callable

from fastapi import Cookie, Depends, Header, Request
from jose import JWTError
from redis.asyncio import Redis

from app.config import settings
from app.core.exceptions import RailMindException, RateLimitExceededError
from app.core.security import decode_access_token
from app.db.session import get_db  # noqa: F401  re-exported for convenience

__all__ = [
    "get_db",
    "get_redis",
    "get_current_user",
    "get_current_user_optional",
    "get_current_user_with_csrf",
    "rate_limit",
]


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


# ─── Rate limiting ────────────────────────────────────────────────────────────


def _client_ip(request: Request) -> str:
    """
    Best-effort client IP. Railway/Vercel sit behind proxies, so the real
    client is in X-Forwarded-For (first hop); fall back to the socket peer.
    """
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def rate_limit(*, limit: int, window_seconds: int = 60, scope: str) -> Callable:
    """
    Redis-backed fixed-window per-IP rate limit, as a FastAPI dependency.

    Each `scope` keeps its own counter, so limits don't bleed across endpoints.

        @router.post(
            "/x",
            dependencies=[Depends(rate_limit(limit=10, scope="auth_x"))],
        )
    """

    async def _enforce(
        request: Request,
        redis: Redis = Depends(get_redis),
    ) -> None:
        key = f"ratelimit:{scope}:{_client_ip(request)}"
        count = await redis.incr(key)
        if count == 1:
            # first hit in this window — start the expiry clock
            await redis.expire(key, window_seconds)
        if count > limit:
            ttl = await redis.ttl(key)
            retry = ttl if ttl and ttl > 0 else window_seconds
            raise RateLimitExceededError(
                message=f"Too many requests. Please try again in {retry} seconds."
            )

    return _enforce


# ─── Current User ─────────────────────────────────────────────────────────────


async def get_current_user(
    access_token: str = Cookie(None, alias="access_token"),
    redis: Redis = Depends(get_redis),
) -> dict:
    # ── 1. Token missing ──────────────────────────────────────────────────────
    if not access_token:
        raise RailMindException(
            code="RM-AUTH-019",
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


# ─── Current User (optional) ──────────────────────────────────────────────────


async def get_current_user_optional(
    access_token: str = Cookie(None, alias="access_token"),
    redis: Redis = Depends(get_redis),
) -> dict | None:
    if not access_token:
        return None
    try:
        payload = decode_access_token(access_token)
    except JWTError:
        return None
    jti = payload.get("jti")
    if jti and await redis.exists(f"blacklist:{jti}"):
        return None
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
            code="RM-AUTH-022",
            message="CSRF token missing",
            status_code=403,
        )

    # ── 3. CSRF header must exist ─────────────────────────────────────────────
    if not csrf_header:
        raise RailMindException(
            code="RM-AUTH-022",
            message="X-CSRF-Token header missing",
            status_code=403,
        )

    # ── 4. Both must match ────────────────────────────────────────────────────
    if csrf_cookie != csrf_header:
        raise RailMindException(
            code="RM-AUTH-022",
            message="CSRF validation failed",
            status_code=403,
        )

    return user
