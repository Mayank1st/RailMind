from twilio.base.exceptions import TwilioRestException
from twilio.rest import Client

from app.config import settings
from app.core.exceptions import WhatsAppDeliveryError

OTP_VALIDITY_MINUTES = 10
OTP_MESSAGE_TEMPLATE = (
    "Your RailMind OTP is {otp_code}. "
    "Valid for {validity_minutes} minutes. Do not share this code with anyone."
)


class WhatsAppClient:
    """Thin sync wrapper around Twilio's WhatsApp API — call from Celery tasks,
    or via run_in_executor from the async request path (Twilio SDK is sync)."""

    def __init__(self) -> None:
        self._client: Client | None = None
        self._from = settings.TWILIO_WHATSAPP_FROM

    def _get_client(self) -> Client:
        if self._client is None:
            self._client = Client(
                settings.TWILIO_ACCOUNT_SID,
                settings.TWILIO_AUTH_TOKEN,
            )
        return self._client

    @staticmethod
    def _to_whatsapp_address(phone: str) -> str:
        """Normalise '+919876543210' -> 'whatsapp:+919876543210'."""
        phone = phone.strip().replace(" ", "")
        if not phone.startswith("+"):
            raise WhatsAppDeliveryError(
                message="Phone must be in E.164 format (e.g. +919876543210)"
            )
        return f"whatsapp:{phone}"

    def send_message(self, to_phone: str, body: str) -> str:
        """Send a free-form WhatsApp message. Returns Twilio message SID."""
        try:
            message = self._get_client().messages.create(
                from_=self._from,
                to=self._to_whatsapp_address(to_phone),
                body=body,
            )
            return message.sid
        except TwilioRestException as exc:
            raise WhatsAppDeliveryError(
                message=f"WhatsApp delivery failed: {exc.msg}"
            ) from exc

    def send_otp(
        self,
        to_phone: str,
        otp_code: str,
        validity_minutes: int = OTP_VALIDITY_MINUTES,
    ) -> str:
        """Send an OTP over WhatsApp. Returns Twilio message SID."""
        body = OTP_MESSAGE_TEMPLATE.format(
            otp_code=otp_code, validity_minutes=validity_minutes
        )
        return self.send_message(to_phone, body)


# Module-level singleton (Twilio Client is reusable & thread-safe for sends)
whatsapp_client = WhatsAppClient()
