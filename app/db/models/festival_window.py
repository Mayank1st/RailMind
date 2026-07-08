from datetime import date

from sqlalchemy import Date, SmallInteger, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import BaseModel


class FestivalWindows(BaseModel):
    __tablename__ = "festival_windows"

    name: Mapped[str] = mapped_column(String(100), nullable=False)
    festival_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    region: Mapped[str] = mapped_column(String(60), nullable=False)
    lookahead_days: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    lookbehind_days: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    demand_tier: Mapped[str] = mapped_column(String(20), nullable=False, index=True)

    def __repr__(self) -> str:
        return (
            f"<FestivalWindows id={self.id} name={self.name} "
            f"date={self.festival_date} tier={self.demand_tier}>"
        )
