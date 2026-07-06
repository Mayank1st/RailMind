import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import Optional

from sqlalchemy import String, and_, cast, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.exceptions import RailMindException
from app.core.security import decrypt_kyc, mask_kyc
from app.db.models.booking import Bookings
from app.db.models.user import UserKYC, UserProfiles, Users
from app.domain.admin.admin_service.admin_audit_service import AdminAuditService
from app.domain.admin.constants.admin_audit import AuditAction, AuditTargetType
from app.domain.admin.constants.admin_users import (
    ASSIGNABLE_ROLES,
    ERR_KYC_NOT_FOUND,
    ERR_USER_NO_CHANGES,
    ERR_USER_NOT_FOUND,
    ERR_USER_SELF_MODIFY,
    ROLE_LABELS,
    STATUS_ACTIVE,
    STATUS_SUSPENDED,
)
from app.domain.admin.dto.admin_users_request_dto import (
    AdminKycReviewRequestDTO,
    AdminUpdateUserRequestDTO,
)
from app.domain.admin.dto.admin_users_response_dto import (
    AdminUserDetailResponseDTO,
    AdminUserSummaryDTO,
    AdminUsersSummaryStatsDTO,
)
from app.domain.auth.constants.auth_user import KycStatus
from app.utils.logger import logger

audit_service = AdminAuditService()


class AdminUsersService:
    """Entities → Users: read (list/tiles/detail) + super-admin audited actions
    (assign role, deactivate/reactivate, KYC approve/reject)."""

    # ── Reads ───────────────────────────────────────────────────────────────

    async def list_users(
        self,
        db: AsyncSession,
        search: Optional[str],
        role: Optional[str],
        kyc_status: Optional[str],
        page: int,
        size: int,
    ) -> tuple[list[AdminUserSummaryDTO], int]:
        conditions = []
        if search:
            like = f"%{search.strip()}%"
            conditions.append(
                or_(
                    Users.email.ilike(like),
                    Users.username.ilike(like),
                    UserProfiles.first_name.ilike(like),
                    UserProfiles.last_name.ilike(like),
                    cast(Users.id, String).ilike(like),
                )
            )
        if role:
            conditions.append(Users.role == role)
        if kyc_status:
            conditions.append(UserKYC.kyc_status == kyc_status)

        base = select(Users).outerjoin(UserProfiles, UserProfiles.user_id == Users.id)
        # inner-join KYC only when filtering by it, else outer (keep KYC-less users)
        if kyc_status:
            base = base.join(UserKYC, UserKYC.user_id == Users.id)
        else:
            base = base.outerjoin(UserKYC, UserKYC.user_id == Users.id)
        if conditions:
            base = base.where(and_(*conditions))

        total = await db.scalar(select(func.count()).select_from(base.subquery()))

        page_query = (
            base.options(selectinload(Users.user_profile), selectinload(Users.user_kyc))
            .order_by(Users.created_at.desc())
            .limit(size)
            .offset((page - 1) * size)
        )
        users = (await db.execute(page_query)).scalars().unique().all()

        counts = await self._booking_counts(db, [u.id for u in users])
        items = [self._serialize_summary(u, counts.get(u.id, 0)) for u in users]
        return items, int(total or 0)

    async def get_users_summary(self, db: AsyncSession) -> AdminUsersSummaryStatsDTO:
        total = await db.scalar(select(func.count()).select_from(Users))

        def _kyc(status: KycStatus):
            return (
                select(func.count())
                .select_from(UserKYC)
                .where(UserKYC.kyc_status == status)
            )

        return AdminUsersSummaryStatsDTO(
            total_users=int(total or 0),
            kyc_passed=int(await db.scalar(_kyc(KycStatus.PASSED)) or 0),
            kyc_pending=int(await db.scalar(_kyc(KycStatus.PENDING)) or 0),
            kyc_failed=int(await db.scalar(_kyc(KycStatus.FAILED)) or 0),
        )

    async def get_user_detail(
        self, user_id: uuid.UUID, db: AsyncSession
    ) -> AdminUserDetailResponseDTO:
        user = await self._load_user(db, user_id)
        return self._serialize_detail(user, await self._booking_count(db, user.id))

    # ── Actions (audited, super-admin only) ─────────────────────────────────

    async def update_user(
        self,
        user_id: uuid.UUID,
        payload: AdminUpdateUserRequestDTO,
        current_user: dict,
        ip: Optional[str],
        db: AsyncSession,
    ) -> AdminUserDetailResponseDTO:
        if payload.role is None and payload.is_active is None:
            raise RailMindException(
                code=ERR_USER_NO_CHANGES,
                message="Nothing to update — provide a role and/or active flag.",
                status_code=400,
            )
        user = await self._load_user(db, user_id)

        # Lockout guard — can't change your own role or disable yourself.
        if str(user.id) == current_user.get("sub"):
            raise RailMindException(
                code=ERR_USER_SELF_MODIFY,
                message="You can't change your own role or status.",
                status_code=403,
            )

        actor_id = current_user.get("sub")
        actor_username = current_user.get("username")

        # ── Role change ───────────────────────────────────────────────────
        if payload.role is not None and payload.role.value != user.role:
            new_role = payload.role.value
            if new_role not in ASSIGNABLE_ROLES:
                raise RailMindException(
                    code=ERR_USER_NO_CHANGES,
                    message=f"Role {new_role} is not assignable.",
                    status_code=422,
                )
            old_role = user.role
            user.role = new_role
            await audit_service.record(
                db,
                actor_id=actor_id,
                actor_username=actor_username,
                action=AuditAction.USER_ROLE_CHANGED.value,
                target_type=AuditTargetType.USER.value,
                target_id=user.id,
                before={"role": old_role},
                after={"role": new_role},
                reason=payload.reason,
                ip=ip,
            )

        # ── Activate / deactivate ─────────────────────────────────────────
        if payload.is_active is not None and payload.is_active != user.is_active:
            was_active = user.is_active
            user.is_active = payload.is_active
            action = (
                AuditAction.USER_REACTIVATED.value
                if payload.is_active
                else AuditAction.USER_DEACTIVATED.value
            )
            await audit_service.record(
                db,
                actor_id=actor_id,
                actor_username=actor_username,
                action=action,
                target_type=AuditTargetType.USER.value,
                target_id=user.id,
                before={"is_active": was_active},
                after={"is_active": payload.is_active},
                reason=payload.reason,
                ip=ip,
            )

        await db.flush()
        logger.info("Admin updated user id=%s by actor=%s", user.id, actor_username)
        return self._serialize_detail(user, await self._booking_count(db, user.id))

    async def review_kyc(
        self,
        user_id: uuid.UUID,
        payload: AdminKycReviewRequestDTO,
        current_user: dict,
        ip: Optional[str],
        db: AsyncSession,
    ) -> AdminUserDetailResponseDTO:
        user = await self._load_user(db, user_id)
        kyc = user.user_kyc
        if kyc is None:
            raise RailMindException(
                code=ERR_KYC_NOT_FOUND,
                message="This user has no KYC record to review.",
                status_code=404,
            )

        before_status = self._kyc_status(kyc)
        if payload.decision == "APPROVE":
            kyc.kyc_status = KycStatus.PASSED
            # verified_at column is naive — store naive UTC
            kyc.verified_at = datetime.now(timezone.utc).replace(tzinfo=None)
            action = AuditAction.USER_KYC_APPROVED.value
        else:
            kyc.kyc_status = KycStatus.FAILED
            action = AuditAction.USER_KYC_REJECTED.value

        await audit_service.record(
            db,
            actor_id=current_user.get("sub"),
            actor_username=current_user.get("username"),
            action=action,
            target_type=AuditTargetType.KYC.value,
            target_id=user.id,
            before={"kyc_status": before_status},
            after={
                "kyc_status": (
                    KycStatus.PASSED.value
                    if payload.decision == "APPROVE"
                    else KycStatus.FAILED.value
                )
            },
            reason=payload.reason,
            ip=ip,
        )
        await db.flush()
        logger.info(
            "Admin KYC %s user=%s by actor=%s",
            payload.decision,
            user.id,
            current_user.get("username"),
        )
        return self._serialize_detail(user, await self._booking_count(db, user.id))

    # ── Helpers ─────────────────────────────────────────────────────────────

    async def _load_user(self, db: AsyncSession, user_id: uuid.UUID) -> Users:
        result = await db.execute(
            select(Users)
            .options(
                selectinload(Users.user_profile),
                selectinload(Users.user_contact),
                selectinload(Users.user_kyc),
            )
            .where(Users.id == user_id)
        )
        user = result.unique().scalar_one_or_none()
        if user is None:
            raise RailMindException(
                code=ERR_USER_NOT_FOUND,
                message="User not found.",
                status_code=404,
            )
        return user

    async def _booking_count(self, db: AsyncSession, user_id: uuid.UUID) -> int:
        total = await db.scalar(
            select(func.count())
            .select_from(Bookings)
            .where(Bookings.user_id == user_id)
        )
        return int(total or 0)

    async def _booking_counts(self, db: AsyncSession, user_ids: list) -> dict:
        if not user_ids:
            return {}
        result = await db.execute(
            select(Bookings.user_id, func.count(Bookings.id))
            .where(Bookings.user_id.in_(user_ids))
            .group_by(Bookings.user_id)
        )
        return {user_id: count for user_id, count in result.all()}

    @staticmethod
    def _full_name(profile: Optional[UserProfiles]) -> Optional[str]:
        if profile and (profile.first_name or profile.last_name):
            return f"{profile.first_name or ''} {profile.last_name or ''}".strip()
        return None

    @staticmethod
    def _kyc_status(kyc: Optional[UserKYC]) -> Optional[str]:
        if kyc is None or kyc.kyc_status is None:
            return None
        return (
            kyc.kyc_status.value
            if isinstance(kyc.kyc_status, Enum)
            else str(kyc.kyc_status)
        )

    @staticmethod
    def _kyc_document(kyc: Optional[UserKYC]) -> tuple[Optional[str], Optional[str]]:
        if kyc is None:
            return None, None
        try:
            if kyc.pan_number:
                return "PAN", mask_kyc(decrypt_kyc(kyc.pan_number))
            if kyc.aadhaar_number:
                return "Aadhaar", mask_kyc(decrypt_kyc(kyc.aadhaar_number))
        except Exception:
            return None, None
        return None, None

    def _serialize_summary(
        self, user: Users, bookings_count: int
    ) -> AdminUserSummaryDTO:
        return AdminUserSummaryDTO(
            user_id=str(user.id),
            name=self._full_name(user.user_profile) or user.username,
            email=user.email,
            role=user.role,
            role_label=ROLE_LABELS.get(user.role, user.role),
            kyc_status=self._kyc_status(user.user_kyc),
            bookings_count=bookings_count,
            is_active=user.is_active,
            status=STATUS_ACTIVE if user.is_active else STATUS_SUSPENDED,
        )

    def _serialize_detail(
        self, user: Users, lifetime_bookings: int
    ) -> AdminUserDetailResponseDTO:
        contact = user.user_contact
        doc_type, doc_masked = self._kyc_document(user.user_kyc)
        return AdminUserDetailResponseDTO(
            user_id=str(user.id),
            name=self._full_name(user.user_profile) or user.username,
            email=user.email,
            phone=contact.mobile_number if contact else None,
            joined_at=user.created_at,
            lifetime_bookings=lifetime_bookings,
            role=user.role,
            role_label=ROLE_LABELS.get(user.role, user.role),
            is_active=user.is_active,
            status=STATUS_ACTIVE if user.is_active else STATUS_SUSPENDED,
            kyc_status=self._kyc_status(user.user_kyc),
            kyc_document_type=doc_type,
            kyc_document_masked=doc_masked,
            kyc_verified_at=user.user_kyc.verified_at if user.user_kyc else None,
        )
