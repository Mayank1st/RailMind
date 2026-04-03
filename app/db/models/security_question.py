from app.db.base import BaseModel, DB_SCHEMA
from sqlalchemy.orm import mapped_column,Mapped
from sqlalchemy import String

class SecurityQuestion(BaseModel):
    __tablename__ = "security_questions"

    question: Mapped[str] = mapped_column(
    String(100), unique=True, nullable=False, index=True
)


