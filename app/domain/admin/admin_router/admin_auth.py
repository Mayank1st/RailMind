from fastapi import APIRouter, Cookie, Depends, Request, Response
from jose import JWTError
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db, get_redis, rate_limit
from app.core.exceptions import RailMindException
from app.core.permissions import IsAgent
from app.core.response import ok
from app.core.security import decode_admin_mfa_pending_token
from app.domain.admin.admin_service.admin_auth_service import AdminAuthService
from app.domain.admin.constants.admin_auth import (
    ADMIN_MFA_PENDING_COOKIE_NAME,
    ERR_MFA_PENDING_INVALID,
)
from app.domain.admin.dto.admin_auth_request_dto import (
    AdminLoginRequestDTO,
    AdminMfaVerifyRequestDTO,
)

router = APIRouter(tags=["Admin Auth"])

admin_auth_service = AdminAuthService()


def _client_ip(request: Request) -> str | None:
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else None


async def get_mfa_pending_identity(
    admin_mfa_pending: str = Cookie(None, alias=ADMIN_MFA_PENDING_COOKIE_NAME),
) -> dict:
    """Resolve the super-admin who passed the password step from the pre-auth
    cookie. Guards the 2FA setup/verify endpoints."""
    if not admin_mfa_pending:
        raise RailMindException(
            code=ERR_MFA_PENDING_INVALID,
            message="Your login session has expired. Please log in again.",
            status_code=401,
        )
    try:
        return decode_admin_mfa_pending_token(admin_mfa_pending)
    except JWTError:
        raise RailMindException(
            code=ERR_MFA_PENDING_INVALID,
            message="Your login session is invalid. Please log in again.",
            status_code=401,
        )


@router.post(
    "/login",
    dependencies=[Depends(rate_limit(limit=10, scope="admin_login"))],
)
async def admin_login(
    payload: AdminLoginRequestDTO,
    request: Request,
    response: Response,
    db: AsyncSession = Depends(get_db),
    redis: Redis = Depends(get_redis),
):
    data = await admin_auth_service.login(
        payload, response, db, redis, ip=_client_ip(request)
    )
    message = (
        "Enter your 2-factor code to continue."
        if data.get("mfa_required")
        else "Signed in to the admin console."
    )
    return ok(data=data, message=message)


@router.post("/2fa/setup")
async def admin_setup_mfa(
    mfa_identity: dict = Depends(get_mfa_pending_identity),
    db: AsyncSession = Depends(get_db),
):
    data = await admin_auth_service.setup_mfa(mfa_identity["sub"], db)
    return ok(data=data, message="Scan the QR code in your authenticator app.")


@router.post(
    "/2fa/verify",
    dependencies=[Depends(rate_limit(limit=10, scope="admin_2fa_verify"))],
)
async def admin_verify_mfa(
    payload: AdminMfaVerifyRequestDTO,
    request: Request,
    response: Response,
    mfa_identity: dict = Depends(get_mfa_pending_identity),
    db: AsyncSession = Depends(get_db),
    redis: Redis = Depends(get_redis),
):
    data = await admin_auth_service.verify_mfa(
        code=payload.code,
        mfa_user_id=mfa_identity["sub"],
        remember_me=bool(mfa_identity.get("remember_me", False)),
        response=response,
        db=db,
        redis=redis,
        ip=_client_ip(request),
    )
    return ok(data=data, message="Signed in to the admin console.")


@router.get("/me")
async def admin_me(
    current_user: dict = IsAgent,
    db: AsyncSession = Depends(get_db),
):
    data = await admin_auth_service.get_admin_profile(current_user, db)
    return ok(data=data, message="Admin profile fetched successfully.")


@router.post("/logout")
async def admin_logout(
    request: Request,
    response: Response,
    current_user: dict = IsAgent,
    redis: Redis = Depends(get_redis),
):
    data = await admin_auth_service.logout(
        current_user, response, redis, ip=_client_ip(request)
    )
    return ok(data=data, message="Logged out successfully.")
