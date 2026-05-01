from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy import String, Integer, Boolean, ForeignKey, Index
from sqlalchemy.dialects.postgresql import UUID

from app.db.base import BaseModel, DB_SCHEMA


class Passengers(BaseModel):
    __tablename__ = "passengers"

    user_id: Mapped[UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey(f"{DB_SCHEMA}.users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    full_name: Mapped[str] = mapped_column(String(100), nullable=False)
    age: Mapped[int] = mapped_column(Integer, nullable=False)
    gender: Mapped[str] = mapped_column(String(10), nullable=False)
    id_type: Mapped[str | None] = mapped_column(String(20), nullable=True)
    id_number: Mapped[str | None] = mapped_column(String(30), nullable=True)
    berth_preference: Mapped[str] = mapped_column(
        String(5), nullable=False, default="NP"
    )
    is_primary: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    user = relationship("Users", back_populates="passengers")

    __table_args__ = (
        Index(
            "uix_passengers_one_primary_per_user",
            "user_id",
            postgresql_where="is_primary = true",
            unique=True,
        ),
        {"schema": DB_SCHEMA},
    )

    def __repr__(self) -> str:
        return (
            f"<Passengers {self.full_name} age={self.age} "
            f"gender={self.gender} user={self.user_id}>"
        )
