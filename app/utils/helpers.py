from datetime import datetime, timezone, date, timedelta
import pytz


def get_utc_timezone():
    return datetime.now(timezone.utc).replace(tzinfo=None)


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
