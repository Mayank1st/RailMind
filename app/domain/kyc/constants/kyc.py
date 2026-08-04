from enum import Enum

# OCR KYC — read an Aadhaar / PAN image and hand the fields back for the user to
# confirm. The AI never writes to user_kyc and never sets kyc_status: the user
# confirms via PATCH /auth/profile, an admin approves via the existing review flow.
#
# Documents go to a PRIVATE Supabase bucket (settings.SUPABASE_KYC_BUCKET) and are
# only ever reached through a short-lived signed URL.

# ─── Error codes (RM-KYC-NNN) ────────────────────────────────────────────────

ERR_IMAGE_TOO_LARGE = "RM-KYC-001"
ERR_INVALID_IMAGE_TYPE = "RM-KYC-002"
ERR_IMAGE_UNREADABLE = "RM-KYC-003"  # bytes aren't a decodable image
ERR_OCR_FAILED = "RM-KYC-004"  # vision model errored / returned no usable JSON
ERR_NOTHING_EXTRACTED = "RM-KYC-005"  # model responded, but every field was null

# ─── Document types ──────────────────────────────────────────────────────────


class DocumentType(str, Enum):
    AADHAAR = "AADHAAR"
    PAN = "PAN"


# Fields the model is asked for, per document. Also drives `unreadable_fields`.
DOCUMENT_FIELDS: dict[str, tuple[str, ...]] = {
    DocumentType.AADHAAR.value: ("name", "aadhaar_number", "date_of_birth", "gender"),
    DocumentType.PAN.value: ("name", "pan_number", "date_of_birth", "father_name"),
}

# The one field per document that makes the whole extraction worth anything.
DOCUMENT_KEY_FIELD: dict[str, str] = {
    DocumentType.AADHAAR.value: "aadhaar_number",
    DocumentType.PAN.value: "pan_number",
}

# ─── Upload limits ───────────────────────────────────────────────────────────

MAX_KYC_IMAGE_MB = 5
BYTES_PER_MB = 1024 * 1024
ALLOWED_KYC_IMAGE_TYPES = frozenset({"image/jpeg", "image/png", "image/webp"})

# ─── Image normalisation (Pillow) ────────────────────────────────────────────

# Downscaling before upload keeps the signed-URL fetch small and, more importantly,
# re-encoding drops EXIF — a phone photo of an Aadhaar card carries GPS otherwise.
MAX_IMAGE_EDGE_PX = 1600
JPEG_QUALITY = 85
NORMALISED_CONTENT_TYPE = "image/jpeg"
NORMALISED_EXTENSION = ".jpg"

# ─── Vision call ─────────────────────────────────────────────────────────────

SIGNED_URL_TTL_SECONDS = 300  # only needs to outlive one model call + a retry
# Admin review URL — longer, so it stays valid while an admin reads the card.
ADMIN_KYC_DOC_URL_TTL_SECONDS = 600
OCR_MAX_TOKENS = 512
# The model is non-deterministic and occasionally emits invalid JSON. One retry
# costs a second or two and turns an intermittent 502 into a normal read.
OCR_MAX_ATTEMPTS = 2

# Values that must be normalised before anyone sees or stores them. The model
# is told to strip spaces and sometimes returns "9876 5432 1098" anyway — and a
# spaced number hashes differently from a bare one, which would silently defeat
# the aadhaar_hash / pan_hash dedupe.
COMPACT_FIELDS = frozenset({"aadhaar_number", "pan_number"})
UPPERCASE_FIELDS = frozenset({"pan_number", "gender"})
FIELD_SEPARATORS = " -"
OCR_TEMPERATURE = 0.0  # transcription, not generation — no creativity wanted
# gpt-5-nano takes `max_completion_tokens`, not the client's `max_tokens` default.
OCR_MAX_TOKENS_PARAM = "max_completion_tokens"

# ─── Endpoint ────────────────────────────────────────────────────────────────

RATE_LIMIT_PER_MINUTE = 5  # image upload + vision call — the priciest AI endpoint
RATE_LIMIT_SCOPE = "kyc_ocr"
