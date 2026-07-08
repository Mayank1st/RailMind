from datetime import datetime

from app.schemas.base import BaseDTO


# -- RateLimitItem (one table row) -------------------------------
class RateLimitItemDTO(BaseDTO):
    rate_limit_id: str
    endpoint: str  # ENDPOINT
    window_seconds: int  # WINDOW (seconds; FE maps to "1 min")
    window_label: str  # "1 min"
    limit: int  # LIMIT
    scope_type: str  # PER_USER | PER_IP | GLOBAL
    scope_label: str  # SCOPE "per user"
    current_peak: int  # CURRENT PEAK — live from Redis
    peak_ratio: float  # current_peak / limit (0..1+) for the bar
    status: str  # "ok" | "near" | "at cap"
    created_at: datetime
