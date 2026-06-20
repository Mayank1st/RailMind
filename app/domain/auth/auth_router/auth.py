from fastapi import APIRouter, Depends, Response, Cookie, UploadFile, File
from sqlalchemy.ext.asyncio import AsyncSession
from redis.asyncio import Redis

from app.api.deps import get_current_user, get_db, get_redis, rate_limit
from app.domain.auth.dto.auth_request_dto import (
    ContactDetailsDTO,
    LoginRequestDTO,
    SendOtpDTO,
    VerifyOtpDTO,
    UpdateUserProfileDTO,
)
from app.domain.auth.auth_service.auth_service import AuthService
from app.domain.auth.auth_service.google_auth_service import GoogleAuthService
from app.core.response import created, ok
from app.domain.auth.constants.auth_user import REFRESH_TOKEN_COOKIE_NAME
from app.core.exceptions import RailMindException
from app.domain.auth.dto.google_auth_request_dto import GoogleAuthRequestDTO
from app.domain.auth.dto.google_auth_response_dto import GoogleAuthResponseDTO

router = APIRouter(prefix="/auth", tags=["Auth"])

auth_service = AuthService()


@router.post("/register")
async def create_user_account(
    payload: ContactDetailsDTO,
    db: AsyncSession = Depends(get_db),
    redis: Redis = Depends(get_redis),
):
    data = await auth_service.create_user_account(payload, db, redis)
    return created(data=data, message="Account created. Please verify your email.")


@router.post(
    "/login",
    dependencies=[Depends(rate_limit(limit=10, scope="auth_login"))],
)
async def login_user(
    payload: LoginRequestDTO,
    response: Response,
    db: AsyncSession = Depends(get_db),
    redis: Redis = Depends(get_redis),
):
    data = await auth_service.login_user(payload, response, db, redis)
    return ok(data=data, message="Logged in successfully.")


@router.post(
    "/google",
    dependencies=[Depends(rate_limit(limit=10, scope="auth_google"))],
)
async def google_auth(
    payload: GoogleAuthRequestDTO,
    response: Response,
    db: AsyncSession = Depends(get_db),
    redis: Redis = Depends(get_redis),
):
    service = GoogleAuthService(db)
    user, auth_result = await service.authenticate_with_google(payload.id_token)
    await auth_service.issue_session(user, response, redis)

    message = (
        "Account created via Google."
        if auth_result.is_new_user
        else "Logged in via Google."
    )
    return ok(data=auth_result, message=message)


@router.post(
    "/otp/send",
    dependencies=[Depends(rate_limit(limit=10, scope="auth_otp_send"))],
)
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


@router.patch("/update-profile")
async def update_current_user_profile(
    payload: UpdateUserProfileDTO,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    data = await auth_service.update_current_user_profile(current_user, payload, db)
    return ok(data=data, message="Profile updated successfully.")


@router.post("/upload-profile-photo")
async def upload_profile_photo(
    profile_photo: UploadFile = File(...),
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    data = await auth_service.upload_profile_photo(current_user, profile_photo, db)
    return ok(data=data, message="Profile Photo Updated Successfully.")


@router.post("/logout")
async def logout_user(
    response: Response,
    current_user: dict = Depends(get_current_user),
    redis: Redis = Depends(get_redis),
):
    data = await auth_service.logout_user(current_user, response, redis)
    return ok(data=data, message="Logged out successfully.")
