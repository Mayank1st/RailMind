from pathlib import Path

from fastapi_mail import ConnectionConfig, FastMail, MessageSchema

from app.config import settings
from app.domain.admin.constants.admin_logs import EmailCategory
from app.integrations.email_log_writer import (
    mark_email_failed,
    mark_email_sent,
    record_email_queued,
)
from app.utils.logger import logger

TEMPLATES_DIR = Path(__file__).parent / "email_templates"
LOGO_PATH = Path(__file__).parent.parent / "assets" / "images" / "logo.png"
LOGO_CID = "railmind_logo"  # templates reference it as <img src="cid:railmind_logo">


def load_template(template_name: str, **kwargs) -> str:
    html = (TEMPLATES_DIR / template_name).read_text()
    for key, value in kwargs.items():
        html = html.replace(f"{{{{ {key} }}}}", str(value))
    return html


conf = ConnectionConfig(
    MAIL_USERNAME=settings.EMAIL_SMTP_USER,
    MAIL_PASSWORD=settings.EMAIL_SMTP_PASSWORD,
    MAIL_FROM=settings.MAIL_FROM,
    MAIL_PORT=settings.MAIL_PORT,
    MAIL_SERVER=settings.EMAIL_SMTP_HOST,
    MAIL_STARTTLS=settings.MAIL_STARTTLS,
    MAIL_SSL_TLS=settings.MAIL_SSL_TLS,
)


async def send_email(
    to: str,
    subject: str,
    body: str,
    attachments: list | None = None,
    *,
    template: str | None = None,
    category: str = EmailCategory.OTHER.value,
    context: dict | None = None,
    linked_type: str | None = None,
    linked_label: str | None = None,
    user_id: str | None = None,
    booking_id: str | None = None,
) -> None:
    logger.info(
        "Email send start: to=%s subject=%r via %s:%s",
        to,
        subject,
        settings.EMAIL_SMTP_HOST,
        settings.MAIL_PORT,
    )
    # Persist the attempt (QUEUED) before sending — best-effort, never blocks.
    log_id = await record_email_queued(
        to_email=to,
        subject=subject,
        template=template,
        category=category,
        context=context,
        linked_type=linked_type,
        linked_label=linked_label,
        user_id=user_id,
        booking_id=booking_id,
    )
    attachments = list(attachments or [])
    # Embed the RailMind logo inline (cid:railmind_logo) so it renders in email
    # clients without fetching an external URL (the old Supabase <img> 404'd /
    # got blocked). Only attached when the template actually references the cid.
    if f"cid:{LOGO_CID}" in body and LOGO_PATH.is_file():
        attachments.append(
            {
                "file": str(LOGO_PATH),
                "mime_type": "image",
                "mime_subtype": "png",
                "headers": {
                    "Content-ID": f"<{LOGO_CID}>",
                    "Content-Disposition": f'inline; filename="{LOGO_PATH.name}"',
                },
            }
        )

    message = MessageSchema(
        subject=subject,
        recipients=[to],
        body=body,
        subtype="html",
        attachments=attachments,
    )
    fm = FastMail(conf)
    try:
        await fm.send_message(message)
    except Exception as exc:
        logger.exception("Email send failed: to=%s subject=%r", to, subject)
        await mark_email_failed(log_id, repr(exc))
        raise
    await mark_email_sent(log_id)
    logger.info("Email send ok: to=%s subject=%r", to, subject)
