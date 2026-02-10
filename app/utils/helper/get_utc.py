from datetime import timezone,datetime

def get_utc_timezone():
    return datetime.now(timezone.utc)