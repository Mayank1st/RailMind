from datetime import datetime

from app.schemas.base import BaseDTO


# -- LlmUsageHour (one hourly rollup row) ------------------------
class LlmUsageHourDTO(BaseDTO):
    hour_start: datetime  # start of the hour (UTC)
    hour_label: str  # "09:00" (HOUR column)
    calls: int  # CALLS
    tokens: int  # TOKENS
    rate_limit_429: int  # 429 RATE-LIMIT (status = rate_limited)
    fallback: int  # FALLBACK (any non-ok call)
    avg_latency_ms: int  # AVG LATENCY (ms; FE renders ms/s)
