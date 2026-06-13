from app.db.base import BaseModel, DB_SCHEMA
from sqlalchemy.orm import mapped_column, Mapped
from sqlalchemy import String, Text, Integer
from app.core.constants.faq import FaqCategory


class Faqs(BaseModel):
    __tablename__ = "faqs"

    question: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    answer: Mapped[str] = mapped_column(Text, nullable=False)
    category: Mapped[str] = mapped_column(
        String(50), nullable=False, default=FaqCategory.GENERAL
    )
    display_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    __table_args__ = ({"schema": DB_SCHEMA},)

    def __repr__(self) -> str:
        return f"<Faq id={self.id} question={self.question[:30]}>"
