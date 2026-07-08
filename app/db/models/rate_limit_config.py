from sqlalchemy import Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import BaseModel


class RateLimitConfigs(BaseModel):
    __tablename__ = "rate_limit_configs"

    endpoint: Mapped[str] = mapped_column(
        String(120), nullable=False, unique=True, index=True
    )
    scope_type: Mapped[str] = mapped_column(String(20), nullable=False)
    window_seconds: Mapped[int] = mapped_column(Integer, nullable=False)
    request_limit: Mapped[int] = mapped_column(Integer, nullable=False)

    def __repr__(self) -> str:
        return (
            f"<RateLimitConfigs id={self.id} endpoint={self.endpoint} "
            f"limit={self.request_limit}/{self.window_seconds}s scope={self.scope_type}>"
        )
