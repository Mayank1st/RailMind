from enum import Enum

# ─── Error codes (RM-ADMIN-NTF-NNN) ───────────────────────────────────────────

ERR_TEMPLATE_NOT_FOUND = "RM-ADMIN-NTF-001"
ERR_TEMPLATE_DUPLICATE_KEY = "RM-ADMIN-NTF-002"


# ─── Channel + status ─────────────────────────────────────────────────────────
class NotificationChannel(str, Enum):
    EMAIL = "EMAIL"
    SMS = "SMS"


class TemplateStatus(str, Enum):
    LIVE = "LIVE"
    DRAFT = "DRAFT"


STATUS_LABELS = {
    TemplateStatus.LIVE.value: "live",
    TemplateStatus.DRAFT.value: "draft",
}

CHANNEL_LABELS = {
    NotificationChannel.EMAIL.value: "Email",
    NotificationChannel.SMS.value: "SMS",
}

# ─── Template variables (the "Insert" chips) + preview sample data ────────────

TEMPLATE_VARIABLES = [
    "name",
    "pnr",
    "train",
    "date",
    "seat",
    "amount",
    "code",
    "old",
    "new",
]

PREVIEW_SAMPLE_DATA = {
    "name": "Ananya",
    "pnr": "8274619305",
    "train": "12951 Mumbai Rajdhani",
    "date": "15 Jul",
    "seat": "S4/38",
    "amount": "₹1,240",
    "code": "418293",
    "old": "WL 12",
    "new": "CNF S4/38",
}

# Length of the raw subject/body snippet shown in the list's SUBJECT / PREVIEW.
PREVIEW_TEXT_MAX = 80
