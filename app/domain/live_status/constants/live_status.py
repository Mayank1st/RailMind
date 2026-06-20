# Live train status (RapidAPI IRCTC) — cache + rate-limit knobs.

CACHE_TTL_LIVE_STATUS = 300  # 5 min — fresh window
CACHE_TTL_LIVE_STATUS_STALE = 86400  # 24h — stale fallback when provider is down
RATE_LIMIT_LIVE_STATUS_PER_MINUTE = 5
LIVE_STATUS_PROVIDER_NAME = "train_running_api"

# Redis key namespaces.
LIVE_STATUS_FRESH_PREFIX = "live_status:fresh:"
LIVE_STATUS_STALE_PREFIX = "live_status:stale:"
LIVE_STATUS_QUOTA_PREFIX = "live_status:quota:"
