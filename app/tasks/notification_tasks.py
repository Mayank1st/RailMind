import secrets
import asyncio

from app.integrations.email import load_template, send_email
from app.tasks.celery_app import celery_app
from app.utils.logger import logger


def generate_six_digit_otp() -> int:
    return secrets.randbelow(900000) + 100000


def send_otp_email_impl(user_name: str, email: str) -> int:
    logger.info("OTP email flow: preparing mail user_name=%s to=%s", user_name, email)
    otp = generate_six_digit_otp()
    body = load_template("otp.html", otp=otp, user_name=user_name, validity_minutes=10)

    # ✅ This works ONLY when called from a thread (no running loop in thread)
    new_loop = asyncio.new_event_loop()
    try:
        new_loop.run_until_complete(
            send_email(to=email, subject="Your RailMind OTP Code", body=body)
        )
    finally:
        new_loop.close()

    logger.info("OTP email flow: finished for to=%s", email)
    return otp


@celery_app.task(name="task_send_otp_email", bind=True)
def task_send_otp_email(self, user_name: str, email: str) -> int:
    logger.info(
        "Celery task task_send_otp_email started task_id=%s user_name=%s to=%s",
        self.request.id, user_name, email,
    )
    try:
        otp = send_otp_email_impl(user_name, email)
    except Exception:
        logger.exception(
            "Celery task task_send_otp_email failed task_id=%s to=%s",
            self.request.id, email,
        )
        raise
    logger.info(
        "Celery task task_send_otp_email done task_id=%s to=%s",
        self.request.id, email,
    )
    return otp