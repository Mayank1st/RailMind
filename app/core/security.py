import hmac
import hashlib
import uuid
import secrets
import base64

from cryptography.fernet import Fernet
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError
from typing import Any, Optional
from app.config import settings
from jose import JWTError, jwt
from datetime import datetime, timezone, timedelta

COMMON_PASSWORD_SET = [
    "Test@123",
    "Admin@123",
    "Admin@1234",
    "User@123",
    "Password@123",
    "Password@1234",
    "Welcome@123",
    "Welcome@1234",
    "Login@123",
    "Company@123",
    "Hello@123",
    "Love@123",
    "Iloveyou@123",
    "Pass@1234",
    "PassWord@1",
    "Test@1111",
    "Test@0000",
    "Rahul@123",
    "Amit@1234",
    "Neha@123",
    "Pooja@123",
    "Mayank@123",
    "Krishna@123",
    "Radhe@123",
    "Mahadev@123",
    "India@123",
    "Bharat@123",
    "Delhi@123",
    "Office@123",
    "Work@123",
    "User@2024",
    "Test@2024",
    "Admin@2024",
    "Password@2024",
]


#  Hash Sensistive Data

HMAC_SECRET_KEY = settings.HMAC_SECRET_KEY
KYC_ENCRYPTION_KEY = settings.KYC_ENCRYPTION_KEY
_fernet = Fernet(KYC_ENCRYPTION_KEY.encode())


ph = PasswordHasher(
    time_cost=3,
    memory_cost=102400,
    parallelism=4,
)


def encode_sensistive_data(plain_data: Any) -> str:
    return ph.hash(plain_data)


def verify_encoded_data(plain_data: Any, encoded_data: Any) -> bool:
    try:
        return ph.verify(encoded_data, plain_data)
    except VerifyMismatchError:
        return False


def verify_token_hash(plain_token: str, stored_hash: str) -> bool:
    return hashlib.sha256(plain_token.encode()).hexdigest() == stored_hash


def hmac_kyc(value: str) -> str:
    return hmac.new(
        HMAC_SECRET_KEY.encode(), value.encode(), hashlib.sha256
    ).hexdigest()


def _generate_jti() -> str:
    """Generate a unique JWT ID (used for blacklisting)."""
    return str(uuid.uuid4())


def hash_token(token: str) -> str:
    """One-way hash a refresh token before storing in Redis."""
    return hashlib.sha256(token.encode()).hexdigest()


def generate_csrf_token() -> str:
    """Generate a cryptographically secure CSRF token."""
    return secrets.token_hex(32)


def encrypt_kyc(plain_value: str) -> str:
    """Encrypt Aadhaar/PAN for reversible storage. Returns urlsafe-base64 token."""
    return _fernet.encrypt(plain_value.encode()).decode()


def decrypt_kyc(encrypted_value: str) -> str:
    """Decrypt KYC token back to plaintext. Raises InvalidToken on tamper/wrong key."""
    return _fernet.decrypt(encrypted_value.encode()).decode()


def mask_kyc(plain_value: str, visible_last: int = 4) -> str:
    """Mask all but the last N chars — e.g. 'XXXXXXXX2345' for display."""
    if len(plain_value) <= visible_last:
        return plain_value
    return "X" * (len(plain_value) - visible_last) + plain_value[-visible_last:]


# ─── Access Token ─────────────────────────────────────────────────────────────


def create_access_token(
    user_id: str,
    username: str,
    role: str = "user",
    extra_claims: Optional[dict] = None,
) -> tuple[str, str]:
    jti = _generate_jti()
    now = datetime.now(timezone.utc)
    expire = now + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)

    payload = {
        "sub": str(user_id),  # subject — user identifier
        "username": username,
        "role": role,
        "jti": jti,  # unique token ID for blacklisting
        "iat": now,  # issued at
        "exp": expire,  # expiry
        "type": "access",
    }

    if extra_claims:
        payload.update(extra_claims)

    token = jwt.encode(
        payload,
        settings.JWT_SECRET_KEY,
        algorithm=settings.JWT_ALGORITHM,
    )
    return token, jti


# ─── Refresh Token ────────────────────────────────────────────────────────────


def create_refresh_token(user_id: str) -> tuple[str, str]:
    jti = _generate_jti()
    now = datetime.now(timezone.utc)
    expire = now + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)

    payload = {
        "sub": str(user_id),
        "jti": jti,
        "iat": now,
        "exp": expire,
        "type": "refresh",  # must check this to prevent access token used as refresh
    }

    token = jwt.encode(
        payload,
        settings.JWT_SECRET_KEY,
        algorithm=settings.JWT_ALGORITHM,
    )
    return token, jti


# ─── Decode & Verify ──────────────────────────────────────────────────────────


def decode_token(token: str) -> dict:
    try:
        payload = jwt.decode(
            token,
            settings.JWT_SECRET_KEY,
            algorithms=[settings.JWT_ALGORITHM],
        )
        return payload
    except JWTError:
        raise


def decode_access_token(token: str) -> dict:
    payload = decode_token(token)
    if payload.get("type") != "access":
        raise JWTError("Invalid token type — expected access token")
    return payload


def decode_refresh_token(token: str) -> dict:
    payload = decode_token(token)
    if payload.get("type") != "refresh":
        raise JWTError("Invalid token type — expected refresh token")
    return payload


# ─── Token Expiry Helpers ─────────────────────────────────────────────────────


def get_token_remaining_seconds(payload: dict) -> int:
    """Calculate remaining TTL of a token in seconds (used for Redis blacklist TTL)."""
    exp = payload.get("exp")
    if not exp:
        return 0
    remaining = exp - datetime.now(timezone.utc).timestamp()
    return max(int(remaining), 0)
