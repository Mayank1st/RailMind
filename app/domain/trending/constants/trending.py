from enum import Enum

# ── Weekly compute window ─────────────────────────────────────────────────────
TRENDING_LOOKBACK_DAYS = 7  # search_histories window the Sunday job aggregates

# ── Beat schedule (IST — celery timezone is Asia/Kolkata) ─────────────────────
TRENDING_RUN_HOUR = 23
TRENDING_RUN_MINUTE = 50
TRENDING_RUN_DAY_OF_WEEK = "sun"

# ── Representative-train lookup (Phase-1 search reuse) ────────────────────────
TRENDING_FLEX_DAYS = 3  # journey_date ± window when picking a train for the card
TRENDING_SEARCH_SIZE = 20  # candidates per route — enough to dedupe flex repeats

ERROR_CODE_TRENDING = "RM-TRD-001"

# ── Popular destinations ("Where India's heading" homepage carousel) ──────────
POPULAR_DEST_LIMIT = 6  # top-N destination cards per week
TAGLINE_MAX_LENGTH = 60  # DB column cap; LLM output truncated to this

TAGLINE_FALLBACKS = {
    "RAJDHANI": "Rajdhani route",
    "SHATABDI": "Shatabdi Express",
    "DURONTO": "Duronto route",
    "SUPERFAST": "Superfast corridor",
    "UNKNOWN": "Popular route",
}

# ── Weekly carousel city images (nano-banana-2 via Replicate + Supabase) ──────
CITY_IMAGE_SUBFOLDER = "weekly_crousel_city_images"  # under SUPABASE_TRENDING_FOLDER
CITY_IMAGE_WIDTH = 1200  # 2:1 landscape — covers desktop's widest crop
CITY_IMAGE_HEIGHT = 600
CITY_IMAGE_MAX_BYTES = 200 * 1024  # keep cards fast to load
CITY_IMAGE_WEBP_QUALITIES = (82, 70, 58, 46)  # tried in order until under the cap
CITY_IMAGE_ASPECT_RATIO = (
    "16:9"  # closest nano-banana-2 ratio to 2:1; center-cropped after
)
CITY_IMAGE_RESOLUTION = "1K"  # ~2x the 474px display width — sharp on retina
CITY_IMAGE_OUTPUT_FORMAT = "jpg"


class TrendingDemandLevel(str, Enum):
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"
