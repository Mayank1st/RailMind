from datetime import datetime, timezone, date


def get_utc_timezone():
    return datetime.now(timezone.utc)

def analyze_age_using_dob(dob:str):
    birth_date = datetime.strptime(dob, "%Y-%m-%d").date()
    today = date.today()
    age = today.year - birth_date.year

    # Adjust if birthday not yet occurred this year
    if (today.month, today.day) < (birth_date.month, birth_date.day):
        age -= 1

    return age
