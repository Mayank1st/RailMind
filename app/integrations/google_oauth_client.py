# app/integrations/google_oauth_client.py
from dataclasses import dataclass

from google.auth.transport import requests as google_requests
from google.oauth2 import id_token as google_id_token

from app.config import settings
from app.core.exceptions import (
    GoogleEmailUnverifiedError,
    GoogleTokenInvalidError,
)


@dataclass(frozen=True)
class GoogleIdentity:
    google_sub: str
    email: str
    first_name: str | None
    last_name: str | None
    picture_url: str | None


def verify_google_id_token(raw_id_token: str) -> GoogleIdentity:
    try:
        payload = google_id_token.verify_oauth2_token(
            raw_id_token,
            google_requests.Request(),
            audience=settings.GOOGLE_CLIENT_ID,
            clock_skew_in_seconds=10,
        )
    except ValueError as exc:
        raise GoogleTokenInvalidError() from exc

    if not payload.get("email_verified", False):
        raise GoogleEmailUnverifiedError()

    return GoogleIdentity(
        google_sub=payload["sub"],
        email=payload["email"].lower(),
        first_name=payload.get("given_name"),
        last_name=payload.get("family_name"),
        picture_url=payload.get("picture"),
    )
