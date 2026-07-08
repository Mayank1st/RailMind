import json
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
    "RATE_LIMIT_CONFIG_PREFIX",
    "rate_limit_counter_key",
]

RATE_LIMIT_CONFIG_PREFIX = "ratelimit:config:"


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


def rate_limit_counter_key(scope: str, scope_type: str, subject: str) -> str:
    """Redis key for a limiter's fixed-window counter. Shared by the enforcer
    (write) and AdminRateLimitsService (CURRENT PEAK read) so both agree."""
    return f"ratelimit:{scope}:{scope_type}:{subject}"


def _user_id_from_request(request: Request) -> str | None:
    """Best-effort user id from the access_token cookie (no error on failure) —
    used for PER_USER buckets. Not an auth check; just a bucketing key."""
    token = request.cookies.get("access_token")
    if not token:
        return None
    try:
        return decode_access_token(token).get("sub")
    except JWTError:
        return None


def _rate_limit_subject(request: Request, scope_type: str) -> str:
    """The counter subject for the configured scope. PER_USER falls back to the
    IP when the caller is unauthenticated, so an anonymous flood is still bounded."""
    if scope_type == "GLOBAL":
        return "global"
    if scope_type == "PER_USER":
        user_id = _user_id_from_request(request)
        if user_id:
            return f"u:{user_id}"
    return f"ip:{_client_ip(request)}"


async def _resolve_rate_limit(
    redis: Redis, scope: str, default_limit: int, default_window: int
) -> tuple[int, int, str]:
    """Effective (limit, window_seconds, scope_type) for a scope. Reads the
    admin override from Redis; any miss/error falls back to the hardcoded default
    (PER_IP) so a bad config or a Redis blip can never remove protection."""
    try:
        raw = await redis.get(f"{RATE_LIMIT_CONFIG_PREFIX}{scope}")
        if raw:
            cfg = json.loads(raw)
            return (
                int(cfg["limit"]),
                int(cfg["window_seconds"]),
                cfg.get("scope_type", "PER_IP"),
            )
    except Exception:
        # never let config resolution break enforcement — use the default
        pass
    return default_limit, default_window, "PER_IP"


def rate_limit(*, limit: int, window_seconds: int = 60, scope: str) -> Callable:
    """
    Redis-backed fixed-window rate limit, as a FastAPI dependency.

    The `limit` / `window_seconds` passed here are the **defaults**. If an admin
    has configured an override for this `scope` (Config → Rate Limits), the
    dependency applies that instead — including its scope_type (PER_IP /
    PER_USER / GLOBAL). If no override exists or the lookup fails, the defaults
    apply, so protection is never removed.

        @router.post(
            "/x",
            dependencies=[Depends(rate_limit(limit=10, scope="auth_x"))],
        )
    """

    async def _enforce(
        request: Request,
        redis: Redis = Depends(get_redis),
    ) -> None:
        eff_limit, eff_window, scope_type = await _resolve_rate_limit(
            redis, scope, limit, window_seconds
        )
        subject = _rate_limit_subject(request, scope_type)
        key = rate_limit_counter_key(scope, scope_type, subject)
        count = await redis.incr(key)
        if count == 1:
            # first hit in this window — start the expiry clock
            await redis.expire(key, eff_window)
        if count > eff_limit:
            ttl = await redis.ttl(key)
            retry = ttl if ttl and ttl > 0 else eff_window
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
