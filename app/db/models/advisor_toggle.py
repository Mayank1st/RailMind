from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import BaseModel


class AdvisorToggles(BaseModel):
    __tablename__ = "advisor_toggles"

    advisor_key: Mapped[str] = mapped_column(
        String(30), nullable=False, unique=True, index=True
    )
    state: Mapped[str] = mapped_column(String(20), nullable=False)

    def __repr__(self) -> str:
        return f"<AdvisorToggles {self.advisor_key}={self.state}>"
