from sqlalchemy import String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import BaseModel


class NotificationTemplates(BaseModel):
    __tablename__ = "notification_templates"

    template_key: Mapped[str] = mapped_column(
        String(60), nullable=False, unique=True, index=True
    )
    channel: Mapped[str] = mapped_column(String(10), nullable=False)  # EMAIL | SMS
    subject: Mapped[str | None] = mapped_column(String(200), nullable=True)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(10), nullable=False)  # LIVE | DRAFT

    def __repr__(self) -> str:
        return (
            f"<NotificationTemplates {self.template_key} "
            f"{self.channel}/{self.status}>"
        )
