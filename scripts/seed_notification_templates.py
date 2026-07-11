"""Seed the notification_templates table with the REAL templates the app sends
today (otp_verify + booking_confirmed), so the admin "Notification Templates"
screen shows the live ones. Idempotent — upserts by template_key.

Run:  python scripts/seed_notification_templates.py           # local DB
      APP_ENV=prod python scripts/seed_notification_templates.py   # VM (via tunnel)

NOTE: this only populates the editable store. The actual send path still uses the
HTML files — seeding does NOT change what customers receive.
"""

import asyncio
import sys
from pathlib import Path

# Ensure the project root is on sys.path when running from scripts/
_ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT_DIR))

from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.db.base import DATABASE_URL, DB_SCHEMA
from app.db.models.notification_template import NotificationTemplates

_TEMPLATES_DIR = _ROOT_DIR / "app" / "integrations" / "email_templates"

_engine = create_async_engine(
    DATABASE_URL,
    poolclass=NullPool,
    connect_args={"server_settings": {"search_path": f'"{DB_SCHEMA}"'}},
)
_Session = async_sessionmaker(bind=_engine, expire_on_commit=False)

# The two templates the app actually sends today (see app/tasks/notification_tasks.py).
SEED = [
    {
        "template_key": "otp_verify",
        "channel": "EMAIL",
        "subject": "Your RailMind OTP Code",
        "file": "otp.html",
        "status": "LIVE",
    },
    {
        "template_key": "booking_confirmed",
        "channel": "EMAIL",
        "subject": "Your RailMind ticket · PNR {{pnr}}",
        "file": "ticket_confirmation.html",
        "status": "LIVE",
    },
]


async def main() -> None:
    async with _Session() as db:
        for spec in SEED:
            body = (_TEMPLATES_DIR / spec["file"]).read_text()
            row = (
                await db.execute(
                    select(NotificationTemplates).where(
                        NotificationTemplates.template_key == spec["template_key"]
                    )
                )
            ).scalar_one_or_none()
            if row is None:
                db.add(
                    NotificationTemplates(
                        template_key=spec["template_key"],
                        channel=spec["channel"],
                        subject=spec["subject"],
                        body=body,
                        status=spec["status"],
                    )
                )
                action = "created"
            else:
                row.channel = spec["channel"]
                row.subject = spec["subject"]
                row.body = body
                row.status = spec["status"]
                action = "updated"
            print(
                f"  {action}: {spec['template_key']} ({spec['channel']}, {spec['status']})"
            )
        await db.commit()
    print("Notification templates seeded.")


if __name__ == "__main__":
    asyncio.run(main())
