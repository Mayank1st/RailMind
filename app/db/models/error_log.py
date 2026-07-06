from sqlalchemy import Integer, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import BaseModel


class ErrorLogs(BaseModel):
    """One row per captured application error (RM-coded business errors + 5xx
    crashes + DB errors). Written best-effort from the exception handlers; read
    by the admin Error Logs screen. FK-free standalone record. `trace` is stored
    only for 5xx (server-side) errors — 4xx business errors are expected and
    don't carry a traceback.
    """

    __tablename__ = "error_logs"

    code: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    domain: Mapped[str | None] = mapped_column(String(20), nullable=True, index=True)
    severity: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    status_code: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    message: Mapped[str | None] = mapped_column(Text, nullable=True)
    method: Mapped[str | None] = mapped_column(String(10), nullable=True)
    path: Mapped[str | None] = mapped_column(String(300), nullable=True, index=True)
    exception_type: Mapped[str | None] = mapped_column(String(100), nullable=True)
    user_id: Mapped[UUID | None] = mapped_column(
        UUID(as_uuid=True), nullable=True, index=True
    )
    ip: Mapped[str | None] = mapped_column(String(64), nullable=True)
    trace: Mapped[str | None] = mapped_column(Text, nullable=True)

    def __repr__(self) -> str:
        return (
            f"<ErrorLogs id={self.id} code={self.code} "
            f"status={self.status_code} path={self.path}>"
        )
