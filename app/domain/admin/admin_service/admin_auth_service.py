from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import joinedload
from sqlalchemy.ext.asyncio import AsyncSession
from fastapi import Response
from redis.asyncio import Redis

from app.config import settings
from app.core.exceptions import RailMindException
from app.core.permissions import has_minimum_role
from app.core.security import (
    verify_encoded_data,
    create_admin_mfa_pending_token,
    encrypt_secret,
    decrypt_secret,
)
from app.core.totp import (
    generate_totp_secret,
    build_provisioning_uri,
    verify_totp_code,
    build_qr_data_uri,
)
from app.db.models.user import Users
from app.db.models.admin_mfa import AdminMfaSecrets
from app.domain.admin.admin_service.admin_audit_service import AdminAuditService
from app.domain.admin.constants.admin_audit import AuditAction, AuditTargetType
from app.domain.auth.auth_service.auth_service import AuthService
from app.domain.auth.constants.auth_user import UserRole
from app.domain.admin.constants.admin_auth import (
    ADMIN_MFA_PENDING_COOKIE_NAME,
    ADMIN_MFA_PENDING_COOKIE_PATH,
    ADMIN_MFA_PENDING_TTL_SECONDS,
    TOTP_ISSUER,
    TOTP_DIGITS,
    TOTP_INTERVAL_SECONDS,
    TOTP_VALID_WINDOW,
    ADMIN_MFA_MAX_ATTEMPTS,
    ADMIN_MFA_ATTEMPT_PREFIX,
    ERR_INVALID_CREDENTIALS,
    ERR_NOT_ADMIN,
    ERR_ACCOUNT_DISABLED,
    ERR_MFA_PENDING_INVALID,
    ERR_MFA_CODE_INVALID,
    ERR_MFA_TOO_MANY_ATTEMPTS,
    ERR_MFA_NOT_SET_UP,
    ERR_MFA_ALREADY_ENABLED,
)
from app.domain.admin.dto.admin_auth_request_dto import AdminLoginRequestDTO
from app.utils.logger import logger

auth_service = AuthService()
audit_service = AdminAuditService()


class AdminAuthService:
    """Admin-console auth: password login with a role gate, then a mandatory
    TOTP (Google Authenticator) 2FA step for super-admins."""

    async def login(
        self,
        payload: AdminLoginRequestDTO,
        response: Response,
        db: AsyncSession,
        redis: Redis,
        ip: str | None = None,
    ) -> dict:
        email = payload.email.lower().strip()

        result = await db.execute(select(Users).where(Users.email == email))
        user = result.scalar_one_or_none()

        # ── 1. Credentials — generic error to avoid account enumeration ────────
        if (
            user is None
            or user.password is None
            or not verify_encoded_data(payload.password, user.password)
        ):
            await self._record_login_event(
                AuditAction.ADMIN_LOGIN_FAILED.value,
                user_id=str(user.id) if user else None,
                username=email,
                ip=ip,
                reason="invalid_credentials",
            )
            raise RailMindException(
                code=ERR_INVALID_CREDENTIALS,
                message="Invalid email or password.",
                status_code=401,
            )

        # ── 2. Role gate — non-admins get the access-denied screen ────────────
        if not has_minimum_role(user.role, UserRole.AGENT):
            await self._record_login_event(
                AuditAction.ADMIN_LOGIN_FAILED.value,
                user_id=str(user.id),
                username=email,
                ip=ip,
                reason="not_admin",
            )
            raise RailMindException(
                code=ERR_NOT_ADMIN,
                message="You don't have access to the admin console.",
                status_code=403,
            )

        # ── 3. Account active ─────────────────────────────────────────────────
        if not user.is_active:
            await self._record_login_event(
                AuditAction.ADMIN_LOGIN_FAILED.value,
                user_id=str(user.id),
                username=email,
                ip=ip,
                reason="account_disabled",
            )
            raise RailMindException(
                code=ERR_ACCOUNT_DISABLED,
                message="This account is disabled. Please contact a super-admin.",
                status_code=403,
            )

        # ── 4a. Super-admin → mandatory 2FA (no session yet) ──────────────────
        if has_minimum_role(user.role, UserRole.ADMIN):
            mfa_row = await self._get_secret_row(db, user.id)
            enrolled = bool(mfa_row and mfa_row.is_enabled)

            pending_token = create_admin_mfa_pending_token(
                user_id=str(user.id),
                ttl_seconds=ADMIN_MFA_PENDING_TTL_SECONDS,
                remember_me=payload.trust_device,
            )
            self._set_mfa_pending_cookie(response, pending_token)

            logger.info(
                "Admin password step OK, 2FA required user_id=%s enrolled=%s",
                user.id,
                enrolled,
            )
            return {
                "mfa_required": True,
                "mfa_enrolled": enrolled,
                "role": user.role,
            }

        # ── 4b. Support-admin (AGENT) → full session immediately ──────────────
        session = await auth_service.issue_session(
            user, response, redis, remember_me=payload.trust_device
        )
        await self._record_login_event(
            AuditAction.ADMIN_LOGIN.value,
            user_id=str(user.id),
            username=user.username or email,
            ip=ip,
            reason="agent_no_2fa",
        )
        logger.info("Support-admin logged in (no 2FA) user_id=%s", user.id)
        return {"mfa_required": False, **session}

    async def setup_mfa(self, mfa_user_id: str, db: AsyncSession) -> dict:
        user = await self._get_admin_or_raise(mfa_user_id, db)

        mfa_row = await self._get_secret_row(db, user.id)
        if mfa_row and mfa_row.is_enabled:
            raise RailMindException(
                code=ERR_MFA_ALREADY_ENABLED,
                message="Two-factor authentication is already set up for this account.",
                status_code=409,
            )

        secret = generate_totp_secret()
        encrypted = encrypt_secret(secret)

        if mfa_row:
            # re-enrolling a not-yet-confirmed secret — overwrite it
            mfa_row.secret_encrypted = encrypted
            mfa_row.is_enabled = False
            mfa_row.confirmed_at = None
        else:
            mfa_row = AdminMfaSecrets(
                user_id=user.id,
                secret_encrypted=encrypted,
                is_enabled=False,
            )
            db.add(mfa_row)
        await db.flush()

        provisioning_uri = build_provisioning_uri(
            secret=secret,
            account_name=user.email,
            issuer=TOTP_ISSUER,
            digits=TOTP_DIGITS,
            interval_seconds=TOTP_INTERVAL_SECONDS,
        )
        logger.info("Admin MFA setup generated user_id=%s", user.id)
        return {
            "secret": secret,  # for manual entry if the QR can't be scanned
            "otpauth_uri": provisioning_uri,
            "qr_data_uri": build_qr_data_uri(provisioning_uri),
        }

    async def verify_mfa(
        self,
        code: str,
        mfa_user_id: str,
        remember_me: bool,
        response: Response,
        db: AsyncSession,
        redis: Redis,
        ip: str | None = None,
    ) -> dict:
        attempt_key = f"{ADMIN_MFA_ATTEMPT_PREFIX}{mfa_user_id}"

        # ── 1. Brute-force guard ──────────────────────────────────────────────
        attempts = await redis.get(attempt_key)
        if attempts and int(attempts) >= ADMIN_MFA_MAX_ATTEMPTS:
            await self._record_login_event(
                AuditAction.ADMIN_LOGIN_FAILED.value,
                user_id=mfa_user_id,
                username=None,
                ip=ip,
                reason="mfa_too_many_attempts",
            )
            raise RailMindException(
                code=ERR_MFA_TOO_MANY_ATTEMPTS,
                message="Too many incorrect codes. Please log in again.",
                status_code=429,
            )

        user = await self._get_admin_or_raise(mfa_user_id, db)

        mfa_row = await self._get_secret_row(db, user.id)
        if mfa_row is None:
            raise RailMindException(
                code=ERR_MFA_NOT_SET_UP,
                message="Two-factor authentication is not set up yet.",
                status_code=400,
            )

        # ── 2. Verify the 6-digit code ────────────────────────────────────────
        secret = decrypt_secret(mfa_row.secret_encrypted)
        if not verify_totp_code(
            secret=secret,
            code=code,
            digits=TOTP_DIGITS,
            interval_seconds=TOTP_INTERVAL_SECONDS,
            valid_window=TOTP_VALID_WINDOW,
        ):
            await redis.incr(attempt_key)
            await redis.expire(attempt_key, ADMIN_MFA_PENDING_TTL_SECONDS)
            await self._record_login_event(
                AuditAction.ADMIN_LOGIN_FAILED.value,
                user_id=str(user.id),
                username=user.username or user.email,
                ip=ip,
                reason="mfa_code_invalid",
            )
            raise RailMindException(
                code=ERR_MFA_CODE_INVALID,
                message="Incorrect code. Please try again.",
                status_code=401,
            )

        # ── 3. First success confirms enrolment ───────────────────────────────
        now = datetime.now(timezone.utc)
        if not mfa_row.is_enabled:
            mfa_row.is_enabled = True
            mfa_row.confirmed_at = now
        mfa_row.last_used_at = now
        await db.flush()

        # ── 4. Issue the real session + clear the pre-auth cookie ─────────────
        await redis.delete(attempt_key)
        session = await auth_service.issue_session(
            user, response, redis, remember_me=remember_me
        )
        self._clear_mfa_pending_cookie(response)

        await self._record_login_event(
            AuditAction.ADMIN_LOGIN.value,
            user_id=str(user.id),
            username=user.username or user.email,
            ip=ip,
            reason="2fa",
        )
        logger.info("Admin 2FA verified, session issued user_id=%s", user.id)
        return {"mfa_required": False, **session}

    async def get_admin_profile(self, current_user: dict, db: AsyncSession) -> dict:
        user_id = current_user.get("sub")

        result = await db.execute(
            select(Users)
            .options(joinedload(Users.user_profile))
            .where(Users.id == user_id)
        )
        user = result.unique().scalar_one_or_none()
        if user is None:
            raise RailMindException(
                code=ERR_MFA_PENDING_INVALID,
                message="Admin account not found.",
                status_code=404,
            )

        profile = user.user_profile
        full_name = None
        if profile:
            full_name = f"{profile.first_name} {profile.last_name}".strip()

        mfa_row = await self._get_secret_row(db, user.id)
        return {
            "id": str(user.id),
            "email": user.email,
            "username": user.username,
            "role": user.role,
            "full_name": full_name,
            "mfa_enabled": bool(mfa_row and mfa_row.is_enabled),
        }

    async def logout(
        self,
        current_user: dict,
        response: Response,
        redis: Redis,
        ip: str | None = None,
    ) -> dict:
        result = await auth_service.logout_user(current_user, response, redis)
        await self._record_login_event(
            AuditAction.ADMIN_LOGOUT.value,
            user_id=current_user.get("sub"),
            username=current_user.get("username"),
            ip=ip,
            reason=None,
        )
        return result

    # ── Helpers ───────────────────────────────────────────────────────────────

    @staticmethod
    async def _record_login_event(
        action: str,
        *,
        user_id: str | None,
        username: str | None,
        ip: str | None,
        reason: str | None,
    ) -> None:
        """Best-effort auth-event audit row (own txn, never raises). The admin is
        both actor and target of their own login/logout."""
        await audit_service.record_event(
            actor_id=user_id,
            actor_username=username,
            action=action,
            target_type=AuditTargetType.AUTH.value,
            target_id=user_id,
            reason=reason,
            ip=ip,
        )

    async def _get_secret_row(
        self, db: AsyncSession, user_id
    ) -> AdminMfaSecrets | None:
        result = await db.execute(
            select(AdminMfaSecrets).where(AdminMfaSecrets.user_id == user_id)
        )
        return result.scalar_one_or_none()

    async def _get_admin_or_raise(self, user_id: str, db: AsyncSession) -> Users:
        """Re-load the user from the pre-auth token's subject and re-assert the
        super-admin gate — role/status may have changed since the password step."""
        result = await db.execute(select(Users).where(Users.id == user_id))
        user = result.scalar_one_or_none()
        if (
            user is None
            or not user.is_active
            or not has_minimum_role(user.role, UserRole.ADMIN)
        ):
            raise RailMindException(
                code=ERR_MFA_PENDING_INVALID,
                message="Your login session is invalid. Please log in again.",
                status_code=401,
            )
        return user

    @staticmethod
    def _set_mfa_pending_cookie(response: Response, token: str) -> None:
        response.set_cookie(
            key=ADMIN_MFA_PENDING_COOKIE_NAME,
            value=token,
            httponly=True,
            secure=settings.cookie_secure,
            samesite=settings.cookie_samesite,
            max_age=ADMIN_MFA_PENDING_TTL_SECONDS,
            path=ADMIN_MFA_PENDING_COOKIE_PATH,
        )

    @staticmethod
    def _clear_mfa_pending_cookie(response: Response) -> None:
        response.delete_cookie(
            key=ADMIN_MFA_PENDING_COOKIE_NAME,
            path=ADMIN_MFA_PENDING_COOKIE_PATH,
            secure=settings.cookie_secure,
            samesite=settings.cookie_samesite,
        )
