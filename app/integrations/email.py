from pathlib import Path

from fastapi_mail import ConnectionConfig, FastMail, MessageSchema

from app.config import settings
from app.utils.logger import logger

TEMPLATES_DIR = Path(__file__).parent / "email_templates"


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
    to: str, subject: str, body: str, attachments: list | None = None
) -> None:
    logger.info(
        "Email send start: to=%s subject=%r via %s:%s",
        to,
        subject,
        settings.EMAIL_SMTP_HOST,
        settings.MAIL_PORT,
    )
    message = MessageSchema(
        subject=subject,
        recipients=[to],
        body=body,
        subtype="html",
        attachments=attachments or [],
    )
    fm = FastMail(conf)
    try:
        await fm.send_message(message)
    except Exception:
        logger.exception("Email send failed: to=%s subject=%r", to, subject)
        raise
    logger.info("Email send ok: to=%s subject=%r", to, subject)
