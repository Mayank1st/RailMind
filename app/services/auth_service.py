import unicodedata
import asyncio
from enum import Enum
from jose import JWTError


from sqlalchemy.orm import joinedload
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from fastapi import Response

from app.db.models.user import (
    UserContacts,
    UserKYC,
    UserProfiles,
    Users,
)
from app.utils.helpers import analyze_age_using_dob
from app.schemas.auth import ContactDetails, LoginRequest
from app.core.security import (
    COMMON_PASSWORD_SET,
    encode_sensistive_data,
    hmac_kyc,
)
from app.core.exceptions import RailMindException
from app.tasks.notification_tasks import send_otp_email_impl
from app.utils.logger import logger
from app.core.constants.auth_user import (
    UserRole,
    ACCESS_TOKEN_COOKIE_NAME,
    REFRESH_TOKEN_COOKIE_NAME,
    CSRF_TOKEN_COOKIE_NAME,
    REFRESH_TOKEN_COOKIE_PATH,
)
from app.config import settings
from redis.asyncio import Redis
from app.core.security import (
    create_access_token,
    create_refresh_token,
    generate_csrf_token,
    hash_token,
    verify_encoded_data,
    decode_refresh_token,
    verify_token_hash,
)

# ─── OTP Constants ────────────────────────────────────────────────────────────
OTP_MAX_ATTEMPTS = 3
OTP_TTL_SECONDS = 600
OTP_REDIS_PREFIX = "otp:"
OTP_ATTEMPT_PREFIX = "otp_attempts:"


class AuthService:

    @staticmethod
    def normalize_payload(payload: ContactDetails) -> ContactDetails:
        payload = payload.model_copy()
        payload.username = unicodedata.normalize(
            "NFKC", payload.username.strip().lower()
        )
        payload.email = unicodedata.normalize("NFKC", payload.email.strip().lower())
        payload.preferred_language = payload.preferred_language.strip().title()
        payload.security_question = payload.security_question.strip()
        payload.security_answer = payload.security_answer.strip()
        payload.first_name = payload.first_name.strip().title()
        payload.last_name = payload.last_name.strip().title()
        payload.mobile_number = payload.mobile_number.replace(" ", "").replace("-", "")
        if payload.aadhaar_number:
            payload.aadhaar_number = payload.aadhaar_number.strip()
        if payload.pan_number:
            payload.pan_number = payload.pan_number.strip().upper()
        if payload.landline_number:
            payload.landline_number = (
                payload.landline_number.strip().replace(" ", "").replace("-", "")
            )
        if payload.address_line1:
            payload.address_line1 = payload.address_line1.strip().title()
        if payload.street:
            payload.street = payload.street.strip().title()
        if payload.state:
            payload.state = payload.state.strip().title()
        if isinstance(payload.nationality, str):
            payload.nationality = payload.nationality.strip().upper()
        if hasattr(payload, "pin_code") and payload.pin_code:
            payload.pin_code = payload.pin_code.strip()
        if payload.country:
            payload.country = payload.country.strip().upper()
        return payload

    async def create_user_account(
        self, payload: ContactDetails, db: AsyncSession, redis: Redis
    ) -> dict:
        payload = self.normalize_payload(payload)

        # ── 1. Age check ──────────────────────────────────────────────────────
        age = analyze_age_using_dob(payload.date_of_birth)
        if age < 18:
            raise RailMindException(
                code="RM-AUTH-007",
                message="User must be at least 18 years old",
                status_code=403,
            )

        # ── 2. Password policy ────────────────────────────────────────────────
        if payload.password == payload.email or payload.password == payload.username:
            raise RailMindException(
                code="RM-AUTH-008",
                message="Password must not match your email or username",
                status_code=422,
            )
        if payload.password in COMMON_PASSWORD_SET:
            raise RailMindException(
                code="RM-AUTH-009",
                message="Password is too common. Please choose a stronger password",
                status_code=422,
            )

        # ── 3. Mobile uniqueness ──────────────────────────────────────────────
        result = await db.execute(
            select(UserContacts).where(
                UserContacts.mobile_number == payload.mobile_number
            )
        )
        if result.scalar_one_or_none():
            raise RailMindException(
                code="RM-AUTH-010",
                message="Mobile number already registered",
                status_code=409,
            )

        # ── 4. Email / username uniqueness ────────────────────────────────────
        result = await db.execute(
            select(Users).where(
                or_(Users.email == payload.email, Users.username == payload.username)
            )
        )
        if result.scalar_one_or_none():
            raise RailMindException(
                code="RM-AUTH-005",
                message="Email or username already exists. Please login",
                status_code=409,
            )

        # ── 5. KYC uniqueness ─────────────────────────────────────────────────
        aadhaar_hmac = (
            hmac_kyc(payload.aadhaar_number) if payload.aadhaar_number else None
        )
        pan_hmac = hmac_kyc(payload.pan_number) if payload.pan_number else None

        kyc_conditions = []
        if aadhaar_hmac:
            kyc_conditions.append(UserKYC.aadhaar_number == aadhaar_hmac)
        if pan_hmac:
            kyc_conditions.append(UserKYC.pan_number == pan_hmac)

        if kyc_conditions:
            result = await db.execute(
                select(UserKYC)
                .options(joinedload(UserKYC.user))
                .where(or_(*kyc_conditions))
            )
            if result.scalar_one_or_none():
                raise RailMindException(
                    code="RM-AUTH-006",
                    message="KYC documents already linked to another account",
                    status_code=409,
                )

        # ── 6. Hash sensitive data ────────────────────────────────────────────
        hashed_password = encode_sensistive_data(payload.password)
        hashed_security_answer = encode_sensistive_data(payload.security_answer)

        def _enum_str(v) -> str:
            return v.value if isinstance(v, Enum) else str(v)

        # ── 7. Persist user + profile + contact + KYC ────────────────────────
        new_user = Users(
            username=payload.username,
            email=payload.email,
            password=hashed_password,
            role=UserRole.USER,
            is_email_verified=False,
            is_mobile_verified=False,
            preferred_language=payload.preferred_language,
            security_question=payload.security_question,
            security_answer_hash=hashed_security_answer,
        )
        db.add(new_user)
        await db.flush()

        db.add(
            UserProfiles(
                user_id=new_user.id,
                first_name=payload.first_name,
                last_name=payload.last_name,
                gender=payload.gender,
                date_of_birth=payload.date_of_birth,
                marital_status=payload.marital_status,
                nationality=payload.nationality,
                occupation_type=_enum_str(payload.occupation_type),
                occupation=_enum_str(payload.occupation),
            )
        )
        db.add(
            UserContacts(
                user_id=new_user.id,
                mobile_number=payload.mobile_number,
                address_line1=payload.address_line1,
                street=payload.street,
                state=payload.state,
                pin_code=payload.pin_code,
                country=payload.country,
                landline_number=payload.landline_number,
            )
        )

        if aadhaar_hmac or pan_hmac:
            db.add(
                UserKYC(
                    user_id=new_user.id,
                    aadhaar_number=aadhaar_hmac,
                    pan_number=pan_hmac,
                )
            )

        # ── 8. Send OTP ───────────────────────────────────────────────────────
        await self.send_otp(email=new_user.email, db=db, redis=redis)

        # ── 9. Return minimal safe response ───────────────────────────────────
        return {
            "id": str(new_user.id),
            "email": new_user.email,
            "username": new_user.username,
        }

    async def login_user(
        self,
        payload: LoginRequest,
        response: Response,
        db: AsyncSession,
        redis: Redis,
    ) -> dict:

        # ── 1. Find user ──────────────────────────────────────────────────────
        result = await db.execute(
            select(Users).where(
                or_(Users.email == payload.email, Users.username == payload.username)
            )
        )
        user = result.scalar_one_or_none()

        if not user:
            raise RailMindException(
                code="RM-AUTH-001",
                message="Email or username does not exist. Please register",
                status_code=404,
            )

        # ── 2. Verify password ────────────────────────────────────────────────
        if not verify_encoded_data(payload.password, user.password):
            raise RailMindException(
                code="RM-AUTH-002",
                message="Incorrect password",
                status_code=401,
            )

        # ── 3. Check email verified ───────────────────────────────────────────
        if not user.is_email_verified:
            raise RailMindException(
                code="RM-AUTH-003",
                message="Email is not verified. Please verify your email first",
                status_code=403,
            )

        # ── 4. Check account active ───────────────────────────────────────────
        if not user.is_active:
            raise RailMindException(
                code="RM-AUTH-004",
                message="Account is disabled. Please contact support",
                status_code=403,
            )

        # ── 5. Create tokens ──────────────────────────────────────────────────
        access_token, jti = create_access_token(
            user_id=str(user.id),
            username=user.username,
            role=user.role,
        )
        refresh_token, _ = create_refresh_token(user_id=str(user.id))
        csrf_token = generate_csrf_token()

        # ── 6. Store refresh token hash in Redis ──────────────────────────────
        await redis.setex(
            f"refresh_token:{user.id}",
            settings.REFRESH_TOKEN_EXPIRE_DAYS * 24 * 60 * 60,
            hash_token(refresh_token),
        )

        # ── 7. Set cookies ────────────────────────────────────────────────────
        AuthService._set_auth_cookies(
            response=response,
            access_token=access_token,
            refresh_token=refresh_token,
            csrf_token=csrf_token,
        )

        return {
            "id": str(user.id),
            "email": user.email,
            "username": user.username,
            "role": user.role,
        }

    async def send_otp(
        self,
        email: str,
        db: AsyncSession,
        redis: Redis,
    ) -> dict:

        email = email.lower().strip()

        # ── 1. Find user ──────────────────────────────────────────────────────────
        result = await db.execute(select(Users).where(Users.email == email))
        user = result.scalar_one_or_none()

        if not user:
            raise RailMindException(
                code="RM-AUTH-004",
                message="User not found. Please register",
                status_code=404,
            )

        # ── 2. Prevent OTP spam ───────────────────────────────────────────────────
        existing_otp = await redis.get(f"{OTP_REDIS_PREFIX}{email}")
        if existing_otp:
            ttl = await redis.ttl(f"{OTP_REDIS_PREFIX}{email}")
            raise RailMindException(
                code="RM-AUTH-011",
                message=f"OTP already sent. Please wait {ttl} seconds before requesting again",
                status_code=429,
            )

        uname, em = str(user.username), user.email

        try:
            loop = asyncio.get_event_loop()
            otp = await loop.run_in_executor(
                None,  # uses default ThreadPoolExecutor
                send_otp_email_impl,  # sync function to run in thread
                uname,  # args passed positionally
                em,
            )
            logger.info("OTP email sent successfully to=%s", em)
        except Exception:
            logger.exception("OTP send failed for email=%s", em)
            raise RailMindException(
                code="RM-AUTH-012",
                message="Failed to send OTP. Please try again",
                status_code=500,
            )

        # ── 4. Save OTP in Redis ──────────────────────────────────────────────────
        await redis.setex(f"{OTP_REDIS_PREFIX}{email}", OTP_TTL_SECONDS, str(otp))
        await redis.delete(f"{OTP_ATTEMPT_PREFIX}{email}")
        logger.info("OTP saved in Redis for email=%s ttl=%ss", email, OTP_TTL_SECONDS)

        return {
            "email": email,
        }

    async def verify_otp(
        self,
        email: str,
        otp: int,
        db: AsyncSession,
        redis: Redis,
    ) -> dict:

        # ── 1. Check brute force ──────────────────────────────────────────────
        attempts = await redis.get(f"{OTP_ATTEMPT_PREFIX}{email}")
        if attempts and int(attempts) >= OTP_MAX_ATTEMPTS:
            raise RailMindException(
                code="RM-AUTH-013",
                message="Too many incorrect attempts. Please request a new OTP",
                status_code=429,
            )

        # ── 2. Get stored OTP ─────────────────────────────────────────────────
        stored_otp = await redis.get(f"{OTP_REDIS_PREFIX}{email}")
        if not stored_otp:
            raise RailMindException(
                code="RM-AUTH-014",
                message="OTP expired or not found. Please request a new one",
                status_code=400,
            )

        # ── 3. Match OTP ──────────────────────────────────────────────────────
        if str(otp) != stored_otp:
            await redis.incr(f"{OTP_ATTEMPT_PREFIX}{email}")
            await redis.expire(f"{OTP_ATTEMPT_PREFIX}{email}", OTP_TTL_SECONDS)
            current_attempts = int(await redis.get(f"{OTP_ATTEMPT_PREFIX}{email}") or 1)
            remaining = OTP_MAX_ATTEMPTS - current_attempts
            raise RailMindException(
                code="RM-AUTH-015",
                message=f"Incorrect OTP. {remaining} attempts remaining",
                status_code=400,
            )

        # ── 4. Mark email verified ────────────────────────────────────────────
        result = await db.execute(select(Users).where(Users.email == email))
        user = result.scalar_one_or_none()

        if not user:
            raise RailMindException(
                code="RM-AUTH-004",
                message="User not found",
                status_code=404,
            )

        user.is_email_verified = True
        await db.flush()

        # ── 5. Clean up Redis ─────────────────────────────────────────────────
        await redis.delete(f"{OTP_REDIS_PREFIX}{email}")
        await redis.delete(f"{OTP_ATTEMPT_PREFIX}{email}")

        logger.info("Email verified successfully for email=%s", email)

        return {"email": email}

    async def refresh_user_token(
        self,
        refresh_token_value: str,
        response: Response,
        redis: Redis,
        db: AsyncSession,
    ) -> dict:
        # ── 1. Decode and verify refresh token signature + expiry ─────────────────
        try:
            payload = decode_refresh_token(refresh_token_value)
        except JWTError:
            raise RailMindException(
                code="RM-AUTH-002",
                message="Invalid or expired refresh token. Please login again",
                status_code=401,
            )

        user_id = payload.get("sub")

        # ── 2. Check refresh token exists in Redis ────────────────────────────────
        stored_hash = await redis.get(f"refresh_token:{user_id}")

        if not stored_hash:
            raise RailMindException(
                code="RM-AUTH-002",
                message="Session expired. Please login again",
                status_code=401,
            )

        # ── 3. Verify hash matches — prevents stolen token reuse ──────────────────
        if not verify_token_hash(refresh_token_value, stored_hash):
            # hash mismatch means token was already rotated or stolen
            # kill session entirely as a security measure
            await redis.delete(f"refresh_token:{user_id}")
            logger.warning(
                "Refresh token hash mismatch — possible theft. Session killed. user_id=%s",
                user_id,
            )
            raise RailMindException(
                code="RM-AUTH-002",
                message="Session invalid. Please login again",
                status_code=401,
            )

        # ── 4. Fetch latest user data from DB ─────────────────────────────────────
        # always fetch from DB — role/status may have changed since last login
        result = await db.execute(select(Users).where(Users.id == user_id))
        user = result.scalar_one_or_none()

        if not user:
            raise RailMindException(
                code="RM-AUTH-004",
                message="User not found",
                status_code=404,
            )

        if not user.is_active:
            raise RailMindException(
                code="RM-AUTH-004",
                message="Account is disabled. Please contact support",
                status_code=403,
            )

        # ── 5. Issue new access + refresh tokens (rotation) ───────────────────────
        new_access_token, _ = create_access_token(
            user_id=str(user.id),
            username=user.username,
            role=user.role,
        )
        new_refresh_token, _ = create_refresh_token(user_id=str(user.id))
        new_csrf_token = generate_csrf_token()

        # ── 6. Overwrite Redis with new refresh token hash ────────────────────────
        await redis.setex(
            f"refresh_token:{user.id}",
            settings.REFRESH_TOKEN_EXPIRE_DAYS * 24 * 60 * 60,
            hash_token(new_refresh_token),
        )

        # ── 7. Set new cookies ────────────────────────────────────────────────────
        AuthService._set_auth_cookies(
            response=response,
            access_token=new_access_token,
            refresh_token=new_refresh_token,
            csrf_token=new_csrf_token,
        )

        logger.info("Token refreshed successfully for user_id=%s", user_id)

        return {
            "id": str(user.id),
            "email": user.email,
            "username": user.username,
            "role": user.role,
        }

    async def get_current_user_profile(
        self,
        current_user: dict,
        db: AsyncSession,
    ) -> dict:

        user_id = current_user.get("sub")

        # ── Fetch user with all relations in one query ─────────────────────────
        result = await db.execute(
            select(Users)
            .options(
                joinedload(Users.user_profile),
                joinedload(Users.user_contact),
                joinedload(Users.user_kyc),
            )
            .where(Users.id == user_id)
        )
        user = result.unique().scalar_one_or_none()

        if not user:
            raise RailMindException(
                code="RM-AUTH-004",
                message="User not found",
                status_code=404,
            )

        # ── Build response safely ──────────────────────────────────────────────
        profile = user.user_profile
        contact = user.user_contact
        kyc = user.user_kyc

        return {
            "id": str(user.id),
            "username": user.username,
            "email": user.email,
            "role": user.role,
            "is_email_verified": user.is_email_verified,
            "is_mobile_verified": user.is_mobile_verified,
            "preferred_language": user.preferred_language,
            "first_name": profile.first_name if profile else None,
            "last_name": profile.last_name if profile else None,
            "gender": profile.gender if profile else None,
            "date_of_birth": profile.date_of_birth if profile else None,
            "marital_status": profile.marital_status if profile else None,
            "nationality": profile.nationality if profile else None,
            "occupation": profile.occupation if profile else None,
            "mobile_number": contact.mobile_number if contact else None,
            "address_line1": contact.address_line1 if contact else None,
            "street": contact.street if contact else None,
            "state": contact.state if contact else None,
            "pin_code": contact.pin_code if contact else None,
            "country": contact.country if contact else None,
            "kyc_status": kyc.kyc_status if kyc else None,
        }

    async def logout_user(
    self,
    current_user: dict,
    response: Response,
    redis: Redis,
) -> dict:

        user_id = current_user.get("sub")
        jti     = current_user.get("jti")
        exp     = current_user.get("exp")

        # ── 1. Blacklist access token JTI in Redis ────────────────────────────────
        if jti and exp:
            from datetime import datetime, timezone
            remaining = int(exp - datetime.now(timezone.utc).timestamp())
            if remaining > 0:
                await redis.setex(f"blacklist:{jti}", remaining, "1")
                logger.info(
                    "Access token blacklisted jti=%s ttl=%ss user_id=%s",
                    jti, remaining, user_id,
                )

        # ── 2. Delete refresh token from Redis ────────────────────────────────────
        # user cannot get new access tokens after this
        if user_id:
            deleted = await redis.delete(f"refresh_token:{user_id}")
            if deleted:
                logger.info("Refresh token deleted for user_id=%s", user_id)
            else:
                logger.warning(
                    "Refresh token not found in Redis for user_id=%s — already expired or logged out",
                    user_id,
                )

        # ── 3. Clear all three cookies from browser ───────────────────────────────
        response.delete_cookie(
            key=ACCESS_TOKEN_COOKIE_NAME,
            path="/",
        )
        response.delete_cookie(
            key=REFRESH_TOKEN_COOKIE_NAME,
            path=REFRESH_TOKEN_COOKIE_PATH,  
        )
        response.delete_cookie(
            key=CSRF_TOKEN_COOKIE_NAME,
            path="/",
        )

        logger.info("User logged out successfully user_id=%s", user_id)
        return {"user_id": user_id}
    
    @staticmethod
    def _set_auth_cookies(
        response: Response,
        access_token: str,
        refresh_token: str,
        csrf_token: str,
    ) -> None:

        response.set_cookie(
            key=ACCESS_TOKEN_COOKIE_NAME,
            value=access_token,
            httponly=True,
            secure=not settings.DEBUG,
            samesite="lax",
            max_age=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
            path="/",
        )
        response.set_cookie(
            key=REFRESH_TOKEN_COOKIE_NAME,
            value=refresh_token,
            httponly=True,
            secure=not settings.DEBUG,
            samesite="lax",
            max_age=settings.REFRESH_TOKEN_EXPIRE_DAYS * 24 * 60 * 60,
            path=REFRESH_TOKEN_COOKIE_PATH,
        )
        response.set_cookie(
            key=CSRF_TOKEN_COOKIE_NAME,
            value=csrf_token,
            httponly=False,
            secure=not settings.DEBUG,
            samesite="lax",
            max_age=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
            path="/",
        )
