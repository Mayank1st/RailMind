"""
════════════════════════════════════════════════════════════════════════════════
 RailMind — create / promote an admin-console user
════════════════════════════════════════════════════════════════════════════════

 Why: nobody can sign in to the admin console until at least one ADMIN (or AGENT)
 user exists. This script inserts that user (or promotes + resets an existing one).

 HOW TO USE
 ----------
 1. Fill in the CONFIG block below (EMAIL / USERNAME / PASSWORD are mandatory).
    - Use a REAL email domain — reserved TLDs like ".test" are rejected at login.
 2. Make sure the `admin_mfa_secrets` migration is applied first (see note *).
 3. Run it against the DB you want (see the two targets below).

 ── TARGET A: LOCAL DB (your Mac Postgres, :5432) ──────────────────────────────
   python scripts/create_admin.py
   # (no APP_ENV  →  defaults to local  →  .env.local  →  localhost:5432)
   #
   # If you hit "permission denied for table users" locally, `railmind` isn't the
   # table owner on your Mac — run as the owner instead:
   #   DB_USERNAME=macbook DB_PASSWORD=ignored python scripts/create_admin.py

 ── TARGET B: VM PROD DB (104.154.106.231) — pick ONE ──────────────────────────
   # B1) From your Mac, over the SSH tunnel (VM Postgres is not public):
   scripts/db-tunnel.sh                       # opens localhost:5433 → VM Postgres
   APP_ENV=prod python scripts/create_admin.py   # .env.prod → 127.0.0.1:5433
   #
   # B2) Or inside the VM backend container (matches the deploy workflow):
   ssh railmind1st@104.154.106.231
   cd ~/railmind
   docker compose -f docker-compose.prod.yml exec backend python scripts/create_admin.py

 * Apply the migration the same way you target the DB:
     LOCAL : DB_USERNAME=macbook DB_PASSWORD=ignored alembic upgrade head
     PROD  : APP_ENV=prod alembic upgrade head        (tunnel up), or
             docker compose -f docker-compose.prod.yml exec backend alembic upgrade head
════════════════════════════════════════════════════════════════════════════════
"""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import select

from app.core.security import encode_sensistive_data
from app.db.models.user import Users, UserProfiles
from app.db.session import async_session_local
from app.domain.auth.constants.auth_user import UserRole


# ══ CONFIG — fill these in before running ═══════════════════════════════════════
EMAIL = "admin1@railmind.ai"  # REQUIRED — real domain, NOT ".test"        e.g. "admin@railmind.ai"
USERNAME = "superadmin1"  # REQUIRED — 3-30 chars, unique             e.g. "superadmin"
PASSWORD = "Secret@123"  # REQUIRED — strong (8+, upper/digit/@$!%*?&) e.g. "Secret@123"

FIRST_NAME = "Super"  # optional — shown in the console top bar
LAST_NAME = "Admin1"  # optional
ROLE = "ADMIN"  # "ADMIN" = super-admin (full access) | "AGENT" = support-admin
# ════════════════════════════════════════════════════════════════════════════════


async def create_admin(
    email: str,
    username: str,
    password: str,
    first_name: str,
    last_name: str,
    role: str,
) -> None:
    email = email.lower().strip()
    hashed = encode_sensistive_data(password)

    async with async_session_local() as db:
        existing = (
            await db.execute(select(Users).where(Users.email == email))
        ).scalar_one_or_none()

        if existing is not None:
            existing.role = role
            existing.password = hashed
            existing.is_active = True
            existing.is_email_verified = True
            await db.commit()
            print(f"Updated {email}: role={role}, password reset, active + verified.")
            return

        user = Users(
            username=username,
            email=email,
            password=hashed,
            role=role,
            is_email_verified=True,
            is_mobile_verified=False,
        )
        db.add(user)
        await db.flush()
        db.add(
            UserProfiles(
                user_id=user.id,
                first_name=first_name,
                last_name=last_name,
            )
        )
        await db.commit()
        print(f"Created {role} user: {email} (username={username}, id={user.id}).")


def main() -> None:
    missing = [
        name
        for name, value in (
            ("EMAIL", EMAIL),
            ("USERNAME", USERNAME),
            ("PASSWORD", PASSWORD),
        )
        if not value.strip()
    ]
    if missing:
        sys.exit(f"Fill in the CONFIG block first — missing: {', '.join(missing)}")

    if ROLE not in (UserRole.ADMIN.value, UserRole.AGENT.value):
        sys.exit(f"ROLE must be 'ADMIN' or 'AGENT', got {ROLE!r}.")

    asyncio.run(
        create_admin(
            email=EMAIL,
            username=USERNAME,
            password=PASSWORD,
            first_name=FIRST_NAME,
            last_name=LAST_NAME,
            role=ROLE,
        )
    )


if __name__ == "__main__":
    main()
