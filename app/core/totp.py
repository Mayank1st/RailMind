import io
import base64

import pyotp
import qrcode


def generate_totp_secret() -> str:
    """Return a fresh base32 TOTP seed to hand to an authenticator app."""
    return pyotp.random_base32()


def build_provisioning_uri(
    secret: str,
    account_name: str,
    issuer: str,
    digits: int,
    interval_seconds: int,
) -> str:
    """Build the otpauth:// URI encoded into the setup QR code."""
    totp = pyotp.TOTP(secret, digits=digits, interval=interval_seconds)
    return totp.provisioning_uri(name=account_name, issuer_name=issuer)


def verify_totp_code(
    secret: str,
    code: str,
    digits: int,
    interval_seconds: int,
    valid_window: int,
) -> bool:
    """Verify a 6-digit code. `valid_window` accepts adjacent 30s steps to
    tolerate clock drift between server and phone."""
    totp = pyotp.TOTP(secret, digits=digits, interval=interval_seconds)
    return totp.verify(code, valid_window=valid_window)


def build_qr_data_uri(provisioning_uri: str) -> str:
    """Render the provisioning URI as a PNG QR and return it as a
    `data:image/png;base64,...` URI the frontend can drop into an <img>."""
    img = qrcode.make(provisioning_uri)
    buffer = io.BytesIO()
    img.save(buffer, format="PNG")
    encoded = base64.b64encode(buffer.getvalue()).decode("ascii")
    return f"data:image/png;base64,{encoded}"
