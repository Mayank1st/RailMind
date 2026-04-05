from fastapi import APIRouter, Depends, Response, Cookie
from sqlalchemy.ext.asyncio import AsyncSession
from redis.asyncio import Redis

from app.api.deps import get_current_user, get_db, get_redis
from app.schemas.auth import (
    ContactDetails,
    LoginRequest,
    SendOtpDTO,
    VerifyOtpDTO,
)
from app.services.auth_service import AuthService
from app.core.response import APIResponse, created, ok
from app.core.constants.auth_user import REFRESH_TOKEN_COOKIE_NAME
from app.core.exceptions import RailMindException

router = APIRouter(prefix="/auth", tags=["Auth"])

auth_service = AuthService()


@router.post("/register")
async def create_user_account(
    payload: ContactDetails,
    db: AsyncSession = Depends(get_db),
    redis: Redis = Depends(get_redis),
):
    data = await auth_service.create_user_account(payload, db, redis)
    return created(data=data, message="Account created. Please verify your email.")


@router.post("/login")
async def login_user(
    payload: LoginRequest,
    response: Response,
    db: AsyncSession = Depends(get_db),
    redis: Redis = Depends(get_redis),
):
    data = await auth_service.login_user(payload, response, db, redis)
    return ok(data=data, message="Logged in successfully.")


@router.post("/otp/send")
async def send_otp(
    payload: SendOtpDTO,
    db: AsyncSession = Depends(get_db),
    redis: Redis = Depends(get_redis), 
):
    data = await auth_service.send_otp(payload.email, db, redis)
    return created(data=data, message="OTP sent successfully. Valid for 10 minutes.")


@router.post("/otp/verify")
async def verify_otp(
    payload: VerifyOtpDTO,
    db: AsyncSession = Depends(get_db),
    redis: Redis = Depends(get_redis),
):
    data = await auth_service.verify_otp(payload.email, payload.otp, db, redis)
    return ok(data=data, message="Email verified successfully.")


@router.post("/refresh")
async def refresh_user_token(
    response: Response,
    refresh_token: str = Cookie(None, alias=REFRESH_TOKEN_COOKIE_NAME),
    db: AsyncSession = Depends(get_db),
    redis: Redis = Depends(get_redis),
):
    if not refresh_token:
        raise RailMindException(
            code="RM-AUTH-002",
            message="Refresh token missing. Please login again",
            status_code=401,
        )
    data = await auth_service.refresh_user_token(
        refresh_token_value=refresh_token,
        response=response,
        redis=redis,
        db=db,
    )
    return ok(data=data, message="Token refreshed successfully.")


@router.get("/me")
async def get_current_user_profile(
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    data = await auth_service.get_current_user_profile(current_user, db)
    return ok(data=data, message="Profile fetched successfully.")


@router.post("/logout")
async def logout_user(
    response: Response,
    current_user: dict = Depends(get_current_user),
    redis: Redis = Depends(get_redis),
):
    data = await auth_service.logout_user(current_user, response, redis)
    return ok(data=data, message="Logged out successfully.")