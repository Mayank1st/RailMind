from datetime import datetime
from typing import Optional

from app.schemas.base import BaseDTO


# -- NotificationTemplateItem (list row + edit drawer) -----------
class NotificationTemplateItemDTO(BaseDTO):
    template_id: str
    template_key: str  # TEMPLATE
    channel: str  # EMAIL | SMS
    channel_label: str  # "Email" | "SMS" (CHANNEL pill)
    subject: Optional[str]
    body: str
    preview_text: str  # raw subject (email) or body snippet (SMS) — SUBJECT / PREVIEW
    status: str  # LIVE | DRAFT
    status_label: str  # "live" | "draft"
    last_edited: datetime  # LAST EDITED (updated_at)


# -- NotificationTemplatePreview (rendered with sample data) ------
class NotificationTemplatePreviewDTO(BaseDTO):
    subject_rendered: Optional[str]
    body_rendered: str
