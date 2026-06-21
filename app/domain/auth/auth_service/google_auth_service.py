# app/services/google_auth_service.py
import asyncio
import secrets
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.user_oauth_accounts import UserOAuthAccounts
from app.db.models.user import UserContacts, UserProfiles, Users
from app.domain.auth.dto.google_auth_response_dto import GoogleAuthResponseDTO
from app.integrations.google_oauth_client import (
    GoogleIdentity,
    verify_google_id_token,
)
from app.config import settings
from app.core.exceptions import ProviderMismatchError


class GoogleAuthService:
    def __init__(self, db: AsyncSession):
        self.db = db

    # ─────────────────── public API ───────────────────

    async def authenticate_with_google(
        self, raw_id_token: str
    ) -> tuple[Users, GoogleAuthResponseDTO]:
        identity = await asyncio.to_thread(verify_google_id_token, raw_id_token)
        now = datetime.now(timezone.utc)

        # ── Branch 1: returning Google user ──
        oauth_account = await self._get_oauth_account(identity.google_sub)
        if oauth_account is not None:
            oauth_account.last_used_at = now
            user = await self.db.get(Users, oauth_account.user_id)
            return user, self._build_response(user, identity, is_new_user=False)

        # ── Branch 2: existing email user → auto-link ──
        user = await self._get_user_by_email(identity.email)
        if user is not None:
            self._link_google_account(user, identity, now)
            user.is_email_verified = True
            return user, self._build_response(user, identity, is_new_user=False)

        # ── Branch 3: brand-new user ──
        user = await self._create_user_from_google(identity)
        self._link_google_account(user, identity, now)
        return user, self._build_response(user, identity, is_new_user=True)

    # ─────────────────── repository-ish helpers ───────────────────

    async def _get_oauth_account(self, google_sub: str) -> UserOAuthAccounts | None:
        stmt = select(UserOAuthAccounts).where(
            UserOAuthAccounts.provider == settings.GOOGLE_PROVIDER,
            UserOAuthAccounts.provider_user_id == google_sub,
        )
        return (await self.db.execute(stmt)).scalar_one_or_none()

    async def _get_user_by_email(self, email: str) -> Users | None:
        stmt = select(Users).where(Users.email == email)
        return (await self.db.execute(stmt)).scalar_one_or_none()

    # ─────────────────── write helpers ───────────────────

    def _link_google_account(
        self, user: Users, identity: GoogleIdentity, now: datetime
    ) -> None:
        self.db.add(
            UserOAuthAccounts(
                user_id=user.id,
                provider=settings.GOOGLE_PROVIDER,
                provider_user_id=identity.google_sub,
                provider_email=identity.email,
                picture_url=identity.picture_url,
                linked_at=now,
                last_used_at=now,
            )
        )

    async def _create_user_from_google(self, identity: GoogleIdentity) -> Users:
        user = Users(
            username=await self._generate_unique_username(identity.email),
            email=identity.email,
            password=None,
            is_email_verified=True,
            security_question=None,
            security_answer_hash=None,
        )
        self.db.add(user)
        await self.db.flush()

        self.db.add(
            UserProfiles(
                user_id=user.id,
                first_name=identity.first_name or "",
                last_name=identity.last_name or "",
                gender=None,
                marital_status=None,
                profile_photo=identity.picture_url,
            )
        )
        self.db.add(UserContacts(user_id=user.id))
        return user

    async def _generate_unique_username(self, email: str) -> str:
        base = email.split("@")[0][:24].lower()
        candidate = base
        while True:
            stmt = select(Users.id).where(Users.username == candidate)
            if (await self.db.execute(stmt)).scalar_one_or_none() is None:
                return candidate
            candidate = f"{base}_{secrets.token_hex(3)}"

    # ─────────────────── response builder ───────────────────

    @staticmethod
    def _build_response(
        user: Users, identity: GoogleIdentity, is_new_user: bool
    ) -> GoogleAuthResponseDTO:
        return GoogleAuthResponseDTO(
            user_id=str(user.id),
            username=user.username,
            email=user.email,
            is_new_user=is_new_user,
            suggested_first_name=identity.first_name,
            suggested_last_name=identity.last_name,
            picture_url=identity.picture_url,
        )
