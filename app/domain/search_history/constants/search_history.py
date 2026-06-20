# Per-user cap on stored recent searches; older rows are trimmed on each log.
RECENT_SEARCH_MAX = 20

# GET /search-history/recent default + max page size.
RECENT_SEARCH_DEFAULT_LIMIT = 5
RECENT_SEARCH_LIMIT_CAP = RECENT_SEARCH_MAX

# Short TTL — list is user-specific and changes on every search.
RECENT_SEARCH_CACHE_TTL = 60  # seconds

# Redis key namespace for the per-user cached list.
RECENT_SEARCH_CACHE_PREFIX = "recent_searches:"
