# Usage:
#   APP_ENV=local ./venv/bin/python scripts/phase-2/seed_mock_users.py            # seed 20 mock users
#   APP_ENV=local ./venv/bin/python scripts/phase-2/seed_mock_users.py --clean    # delete all mock users
import argparse
import asyncio
import sys
import time
from datetime import date
from pathlib import Path

parser = argparse.ArgumentParser(
    description="Seed mock users + joined profile/contact/kyc rows"
)
parser.add_argument(
    "--count", type=int, default=20, help="number of mock users to seed"
)
parser.add_argument(
    "--password",
    type=str,
    default="Password@123",
    help="plaintext password applied to every mock user (Argon2-hashed before insert)",
)
parser.add_argument(
    "--clean",
    action="store_true",
    help="delete all seeded mock users (and their cascade-linked rows) instead of seeding",
)
args = parser.parse_args()

USER_COUNT = args.count
PLAIN_PASSWORD = args.password
CLEAN = args.clean

# All seeded mock users share this email domain — used to scope cleanup.
MOCK_EMAIL_LIKE = "mock.user%@railmind.test"

# scripts/phase-2/seed_mock_users.py -> repo root is three levels up.
_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(_PROJECT_ROOT))

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.security import encode_sensistive_data
from app.db.base import DATABASE_URL, DB_SCHEMA
from app.db.models.user import UserContacts, UserKYC, UserProfiles, Users
from app.domain.auth.constants.auth_user import (
    Gender,
    KycStatus,
    MaritalStatus,
    UserRole,
)

# ── Mock data pools (deterministic so reruns are idempotent) ──────────────────
FIRST_NAMES = [
    "Aarav",
    "Vivaan",
    "Aditya",
    "Vihaan",
    "Arjun",
    "Reyansh",
    "Ananya",
    "Diya",
    "Saanvi",
    "Ishaan",
    "Kabir",
    "Anika",
    "Myra",
    "Aarush",
    "Riya",
    "Krishna",
    "Ira",
    "Aryan",
    "Kiara",
    "Rohan",
    "Meera",
    "Dev",
    "Tara",
    "Yash",
    "Sara",
]
LAST_NAMES = [
    "Sharma",
    "Verma",
    "Gupta",
    "Iyer",
    "Nair",
    "Reddy",
    "Patel",
    "Singh",
    "Das",
    "Khan",
    "Mehta",
    "Joshi",
    "Rao",
    "Bose",
    "Pillai",
    "Chopra",
    "Malhotra",
    "Banerjee",
    "Kapoor",
    "Menon",
    "Sinha",
    "Ghosh",
    "Nayak",
    "Bhat",
    "Pandey",
]
STATES = [
    ("Maharashtra", "Mumbai", "400001"),
    ("Karnataka", "Bengaluru", "560001"),
    ("Tamil Nadu", "Chennai", "600001"),
    ("Delhi", "New Delhi", "110001"),
    ("West Bengal", "Kolkata", "700001"),
    ("Telangana", "Hyderabad", "500001"),
    ("Gujarat", "Ahmedabad", "380001"),
    ("Rajasthan", "Jaipur", "302001"),
]
GENDERS = [Gender.MALE, Gender.FEMALE, Gender.TRANSGENDER]
MARITALS = [MaritalStatus.MARRIED, MaritalStatus.UNMARRIED]
KYC_STATUSES = [KycStatus.PENDING, KycStatus.PASSED, KycStatus.FAILED]
LANGUAGES = ["English", "Hindi", "Tamil", "Bengali", "Marathi"]
OCCUPATIONS = [
    ("Salaried", "Software Engineer"),
    ("Self-Employed", "Business Owner"),
    ("Government", "Civil Servant"),
    ("Student", "Undergraduate"),
    ("Retired", "Pensioner"),
]


async def clean(session):
    # FK rows in user_profiles/contacts/kyc have ondelete=CASCADE, so deleting
    # the users removes their joined rows too.
    result = await session.execute(
        select(Users.id).where(Users.email.like(MOCK_EMAIL_LIKE))
    )
    ids = [row.id for row in result.fetchall()]
    if not ids:
        print("\n  No mock users found — nothing to clean.")
        return 0
    await session.execute(delete(Users).where(Users.id.in_(ids)))
    await session.commit()
    print(
        f"\n  Deleted {len(ids)} mock users (+ cascade-linked profile/contact/kyc rows)."
    )
    return len(ids)


async def main():
    start_time = time.time()
    print("=" * 60)
    print("  RailMind — Mock User Seeder")
    print("=" * 60)
    if CLEAN:
        print("  Mode:           CLEAN (delete mock users)")
    else:
        print(f"  Users to seed:  {USER_COUNT}")
        print(f"  Password:       {PLAIN_PASSWORD}")
    print(f"  Schema:         {DB_SCHEMA}")
    print("=" * 60)

    if CLEAN:
        engine = create_async_engine(
            DATABASE_URL,
            echo=False,
            pool_size=5,
            max_overflow=5,
            connect_args={"server_settings": {"search_path": f'"{DB_SCHEMA}"'}},
        )
        async_session = async_sessionmaker(
            bind=engine, class_=AsyncSession, expire_on_commit=False
        )
        async with async_session() as session:
            try:
                await clean(session)
            except Exception as e:
                await session.rollback()
                print(f"\n[ERROR] {e}")
                raise
        await engine.dispose()
        print(f"\n{'=' * 60}")
        print(f"  Done in {time.time() - start_time:.1f}s")
        print(f"{'=' * 60}\n")
        return

    # Hash once — Argon2 is expensive; every mock user shares the same password.
    print("\n  Hashing shared password (Argon2)…")
    hashed_password = encode_sensistive_data(PLAIN_PASSWORD)
    hashed_answer = encode_sensistive_data("railmind")

    engine = create_async_engine(
        DATABASE_URL,
        echo=False,
        pool_size=5,
        max_overflow=5,
        connect_args={"server_settings": {"search_path": f'"{DB_SCHEMA}"'}},
    )
    async_session = async_sessionmaker(
        bind=engine, class_=AsyncSession, expire_on_commit=False
    )

    created = 0
    skipped = 0

    async with async_session() as session:
        try:
            existing_result = await session.execute(select(Users.username, Users.email))
            existing_usernames = set()
            existing_emails = set()
            for row in existing_result.fetchall():
                existing_usernames.add(row.username)
                existing_emails.add(row.email)

            for i in range(1, USER_COUNT + 1):
                first = FIRST_NAMES[(i - 1) % len(FIRST_NAMES)]
                last = LAST_NAMES[(i - 1) % len(LAST_NAMES)]
                username = f"mock_{first.lower()}{i:02d}"
                email = f"mock.user{i:02d}@railmind.test"

                if username in existing_usernames or email in existing_emails:
                    skipped += 1
                    print(f"  [{i:02d}] skip — {email} already exists")
                    continue

                state, _city, pin = STATES[(i - 1) % len(STATES)]
                occ_type, occ = OCCUPATIONS[(i - 1) % len(OCCUPATIONS)]
                kyc_status = KYC_STATUSES[(i - 1) % len(KYC_STATUSES)]

                user = Users(
                    username=username,
                    email=email,
                    password=hashed_password,
                    role=UserRole.USER,
                    is_email_verified=(i % 2 == 0),
                    is_mobile_verified=(i % 3 == 0),
                    preferred_language=LANGUAGES[(i - 1) % len(LANGUAGES)],
                    security_question="What is your favourite railway?",
                    security_answer_hash=hashed_answer,
                )
                session.add(user)
                await session.flush()  # populate user.id for the FK rows

                session.add(
                    UserProfiles(
                        user_id=user.id,
                        first_name=first,
                        last_name=last,
                        gender=GENDERS[(i - 1) % len(GENDERS)],
                        date_of_birth=date(
                            1985 + (i % 20), ((i % 12) + 1), ((i % 27) + 1)
                        ),
                        marital_status=MARITALS[(i - 1) % len(MARITALS)],
                        nationality="Indian",
                        occupation_type=occ_type,
                        occupation=occ,
                    )
                )
                session.add(
                    UserContacts(
                        user_id=user.id,
                        mobile_number=f"+9198{i:08d}",
                        address_line1=f"{i} Platform Road",
                        street="Station Street",
                        state=state,
                        pin_code=pin,
                        country="India",
                        landline_number=None,
                    )
                )
                session.add(
                    UserKYC(
                        user_id=user.id,
                        kyc_status=kyc_status,
                    )
                )

                created += 1
                print(f"  [{i:02d}] add  — {email} ({first} {last})")

            await session.commit()
        except Exception as e:
            await session.rollback()
            print(f"\n[ERROR] {e}")
            raise

    await engine.dispose()

    elapsed = time.time() - start_time
    print(f"\n{'=' * 60}")
    print(f"  Done in {elapsed:.1f}s — created {created}, skipped {skipped}")
    print(f"  Login with any seeded email + password: {PLAIN_PASSWORD}")
    print(f"{'=' * 60}\n")


if __name__ == "__main__":
    asyncio.run(main())
