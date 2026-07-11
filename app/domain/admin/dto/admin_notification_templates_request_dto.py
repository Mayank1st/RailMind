from typing import Optional

from pydantic import Field

from app.domain.admin.constants.admin_notification_templates import (
    NotificationChannel,
    TemplateStatus,
)
from app.schemas.base import BaseDTO


# -- CreateTemplateRequest ("New template" drawer) ---------------
class CreateNotificationTemplateRequestDTO(BaseDTO):
    template_key: str = Field(min_length=1, max_length=60)
    channel: NotificationChannel
    subject: Optional[str] = Field(default=None, max_length=200)
    body: str = Field(min_length=1)
    status: TemplateStatus = TemplateStatus.DRAFT  # "Publish live" → LIVE


# -- UpdateTemplateRequest ("Edit template" drawer, partial) -----
class UpdateNotificationTemplateRequestDTO(BaseDTO):
    template_key: Optional[str] = Field(default=None, min_length=1, max_length=60)
    channel: Optional[NotificationChannel] = None
    subject: Optional[str] = Field(default=None, max_length=200)
    body: Optional[str] = Field(default=None, min_length=1)
    status: Optional[TemplateStatus] = None


# -- PreviewTemplateRequest (live preview as you type; no save) ---
class PreviewNotificationTemplateRequestDTO(BaseDTO):
    channel: NotificationChannel
    subject: Optional[str] = Field(default=None, max_length=200)
    body: str = ""
