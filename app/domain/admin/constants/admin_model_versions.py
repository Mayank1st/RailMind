# ─── Error codes (RM-ADMIN-MDL-NNN) ───────────────────────────────────────────

ERR_MODEL_ADVISOR_NOT_FOUND = "RM-ADMIN-MDL-001"
ERR_MODEL_VERSION_NOT_FOUND = "RM-ADMIN-MDL-002"
ERR_MODEL_ARTIFACT_MISSING = (
    "RM-ADMIN-MDL-003"  # can't activate a version with no artifact
)
ERR_MODEL_NOT_ML_VERSION = (
    "RM-ADMIN-MDL-004"  # can't activate the fallback as an ML version
)

# ─── kind ─────────────────────────────────────────────────────────────────────

KIND_ML = "ml"
KIND_FALLBACK = "fallback"

# ─── Per-version status (version-history cards) ───────────────────────────────

VERSION_STATUS_ACTIVE = "active"  # designated active ML version
VERSION_STATUS_PREVIOUS = "previous"  # most-recent non-active ML version
VERSION_STATUS_ARCHIVED = "archived"  # older non-active ML versions
VERSION_STATUS_FALLBACK = "fallback"  # the rules pseudo-version

# ─── Advisor serving status (list row badge) ──────────────────────────────────

SERVING_STATUS_LIVE = "live"  # ML actually serving
SERVING_STATUS_FALLBACK = "fallback"  # rules serving (forced or model down)
SERVING_STATUS_OFF = "off"  # advisor toggled off

# Suffix for the rules-fallback pseudo-version label, e.g. "waitlist-rules".
FALLBACK_LABEL_SUFFIX = "-rules"
FALLBACK_METRIC_TEXT = "Rule-based fallback"
