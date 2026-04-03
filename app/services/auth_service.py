import unicodedata

from sqlalchemy.orm import joinedload
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.user import Users, UserKYC
from app.utils.helpers import analyze_age_using_dob
from app.schemas.auth import ContactDetails
from app.core.security import (
    COMMON_PASSWORD_SET,
    encode_sensistive_data,
    hmac_kyc,
)
from app.core.exceptions import RailMindException
# from app.tasks.notification_tasks import task_send_otp_email


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
        self, payload: ContactDetails, db: AsyncSession
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
            select(Users).where(Users.mobile_number == payload.mobile_number)
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

        # ── 5. KYC uniqueness (HMAC lookup) ───────────────────────────────────
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
            existing_kyc = result.scalar_one_or_none()

            if existing_kyc:
                raise RailMindException(
                    code="RM-AUTH-006",
                    message="KYC documents already linked to another account",
                    status_code=409,
                )

        # ── 6. Hash sensitive data ────────────────────────────────────────────
        hashed_password = encode_sensistive_data(payload.password)
        hashed_security_answer = encode_sensistive_data(payload.security_answer)
        encrypted_aadhaar = (
            encode_sensistive_data(payload.aadhaar_number)
            if payload.aadhaar_number
            else None
        )
        encrypted_pan = (
            encode_sensistive_data(payload.pan_number) if payload.pan_number else None
        )

        # ── 7. Persist user + KYC atomically ──────────────────────────────────
        async with db.begin():
            new_user = Users(
                username=payload.username,
                email=payload.email,
                password_hash=hashed_password,
                full_name=f"{payload.first_name} {payload.last_name}",
                mobile_number=payload.mobile_number,
                preferred_language=payload.preferred_language,
                security_question=payload.security_question,
                security_answer=hashed_security_answer,
                date_of_birth=payload.date_of_birth,
                gender=payload.gender,
                marital_status=payload.marital_status,
                occupation_type=payload.occupation_type,
                occupation=payload.occupation,
                nationality=payload.nationality,
                address_line1=payload.address_line1,
                street=payload.street,
                state=payload.state,
                pin_code=payload.pin_code,
                country=payload.country,
                landline_number=payload.landline_number,
                is_verified=False,  # flipped to True after OTP
                is_active=False,  # flipped to True after OTP
                role="user",
            )
            db.add(new_user)
            await db.flush()  # get new_user.id without committing

            if aadhaar_hmac or pan_hmac:
                new_kyc = UserKYC(
                    user_id=new_user.id,
                    aadhaar_number=aadhaar_hmac,  # HMAC for future lookup
                    pan_number=pan_hmac,  # HMAC for future lookup
                    encrypted_aadhaar=encrypted_aadhaar,  # encrypted for display/audit
                    encrypted_pan=encrypted_pan,
                    is_verified=False,
                )
                db.add(new_kyc)
            # auto-commits here; rolls back entire block on any exception

        # ── 8. Fire OTP (outside transaction — side effect) ───────────────────
        # task_send_otp_email.delay(user_id=str(new_user.id), email=payload.email)

        # ── 9. Return minimal safe response ───────────────────────────────────
        return {
            "id": str(new_user.id),
            "email": new_user.email,
            "username": new_user.username,
        }
