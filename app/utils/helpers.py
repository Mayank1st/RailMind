from datetime import datetime, timezone, date


def get_utc_timezone():
    """UTC wall time as naive datetime.

    PostgreSQL columns use ``TIMESTAMP WITHOUT TIME ZONE``; asyncpg rejects
    mixing those with timezone-aware ``datetime`` values.
    """
    return datetime.now(timezone.utc).replace(tzinfo=None)

def analyze_age_using_dob(dob: date):
    today = date.today()
    age = today.year - dob.year

    if (today.month, today.day) < (dob.month, dob.day):
        age -= 1

    return age
