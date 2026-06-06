import pytz
import filetype

from datetime import datetime, timezone, date, timedelta

ALLOWED_MIME_TYPES = {"image/jpeg", "image/png", "application/pdf"}


def get_utc_timezone():
    return datetime.now(timezone.utc)


def analyze_age_using_dob(dob: date):
    today = date.today()
    age = today.year - dob.year

    if (today.month, today.day) < (dob.month, dob.day):
        age -= 1

    return age


def get_time_after_hours(hours: int) -> str:
    ist = pytz.timezone("Asia/Kolkata")
    now = datetime.now(ist)
    future_time = now + timedelta(hours=hours)
    return future_time.strftime("%H:%M:%S")


def parse_datetime_flexible(value: str) -> datetime:

    value = value.strip()
    formats = [
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d",
        "%d-%m-%Y %H:%M:%S",
        "%d-%m-%Y",
        "%d/%m/%Y %H:%M:%S",
        "%d/%m/%Y",
    ]
    for fmt in formats:
        try:
            return datetime.strptime(value, fmt)
        except ValueError:
            continue

    raise ValueError(f"Unsupported datetime format: {value}")


def get_content_type(file_bytes: bytes) -> str:
    kind = filetype.guess(file_bytes)
    if kind is None:
        return "application/octet-stream"
    return kind.mime
