import secrets
import asyncio
from io import BytesIO

from starlette.datastructures import Headers, UploadFile

from app.integrations.email import load_template, send_email
from app.tasks.celery_app import celery_app
from app.tasks.worker_loop import run_in_worker_loop as _run_in_worker_loop
from app.utils.logger import logger

# Passenger-status → colour for the confirmation email's passenger table.
PASSENGER_STATUS_COLORS = {
    "CNF": "#0F6E56",
    "RAC": "#1D9E75",
    "WL": "#B45309",
    "CAN": "#999999",
}


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
        self.request.id,
        user_name,
        email,
    )
    try:
        otp = send_otp_email_impl(user_name, email)
    except Exception:
        logger.exception(
            "Celery task task_send_otp_email failed task_id=%s to=%s",
            self.request.id,
            email,
        )
        raise
    logger.info(
        "Celery task task_send_otp_email done task_id=%s to=%s",
        self.request.id,
        email,
    )
    return otp


# ── Booking confirmation email (with ticket PDF attached) ─────────────────────


def _build_passenger_rows(passengers: list[dict]) -> str:
    """Build the passenger table rows in Python — load_template only does flat
    `{{ key }}` substitution, so the variable-length list can't loop in HTML."""
    rows = ""
    for p in passengers:
        color = PASSENGER_STATUS_COLORS.get(p["status"], "#555555")
        rows += (
            '<tr style="border-bottom:1px solid #f0f0f0;">'
            f'<td style="font-size:12px;color:#111;padding:8px 10px;">{p["name"]}</td>'
            '<td align="center" style="font-size:12px;color:#555;padding:8px 10px;">'
            f'{p["age"]}/{p["gender"]}</td>'
            '<td align="center" style="font-size:12px;color:#111;padding:8px 10px;">'
            f'{p["seat"]}</td>'
            f'<td align="center" style="font-size:12px;font-weight:600;color:{color};'
            f'padding:8px 10px;">{p["status"]}</td>'
            "</tr>"
        )
    return rows


async def _async_send_booking_confirmation(booking_id: str) -> None:
    from app.db.session import async_session_local
    from app.domain.booking.booking_service.booking_service import BookingService
    from app.domain.booking.booking_service.ticket_pdf import build_ticket_pdf

    booking_service = BookingService()

    async with async_session_local() as db:
        ticket_payload, booking = await booking_service.build_ticket_payload(
            booking_id, db
        )

        recipient = booking.user.email
        profile = booking.user.user_profile
        user_name = (
            profile.first_name
            if profile and profile.first_name
            else booking.user.username
        )

        pdf_bytes = build_ticket_pdf(ticket=ticket_payload)
        fare = ticket_payload["fare_breakdown"]

        body = load_template(
            "ticket_confirmation.html",
            user_name=user_name,
            booking_status=ticket_payload["booking_status"],
            pnr_number=ticket_payload["pnr_number"],
            train_number=ticket_payload["train_number"],
            train_name=ticket_payload["train_name"],
            train_class=ticket_payload["train_class"],
            quota=ticket_payload["quota"],
            journey_date=ticket_payload["journey_date"],
            journey_day=ticket_payload["journey_day"],
            source_station=ticket_payload["source_station"],
            source_name=ticket_payload["source_name"],
            departure_time=ticket_payload["departure_time"],
            dest_station=ticket_payload["dest_station"],
            dest_name=ticket_payload["dest_name"],
            arrival_time=ticket_payload["arrival_time"],
            arrival_day=ticket_payload["arrival_day"] or "",
            duration=ticket_payload["duration"],
            distance_km=ticket_payload["distance_km"],
            passenger_rows=_build_passenger_rows(ticket_payload["passengers"]),
            base_fare=fare["base_fare"],
            reservation_charge=fare["reservation_charge"],
            gst=fare["gst"],
            total_fare=fare["total_fare"],
            chart_status=ticket_payload["chart_status"],
            booked_at=ticket_payload["booked_at"],
        )

        attachment = UploadFile(
            filename=f"ticket_{ticket_payload['pnr_number']}.pdf",
            file=BytesIO(pdf_bytes),
            headers=Headers({"content-type": "application/pdf"}),
        )

        await send_email(
            to=recipient,
            subject=f"Your RailMind ticket · PNR {ticket_payload['pnr_number']}",
            body=body,
            attachments=[attachment],
        )


def send_booking_confirmation_impl(booking_id: str) -> None:
    logger.info("Booking confirmation email: preparing booking_id=%s", booking_id)
    _run_in_worker_loop(_async_send_booking_confirmation(booking_id))
    logger.info("Booking confirmation email: finished booking_id=%s", booking_id)


@celery_app.task(name="task_send_booking_confirmation", bind=True)
def task_send_booking_confirmation(self, booking_id: str) -> None:
    logger.info(
        "Celery task task_send_booking_confirmation started task_id=%s booking_id=%s",
        self.request.id,
        booking_id,
    )
    try:
        send_booking_confirmation_impl(booking_id)
    except Exception:
        logger.exception(
            "Celery task task_send_booking_confirmation failed task_id=%s booking_id=%s",
            self.request.id,
            booking_id,
        )
        raise
    logger.info(
        "Celery task task_send_booking_confirmation done task_id=%s booking_id=%s",
        self.request.id,
        booking_id,
    )
