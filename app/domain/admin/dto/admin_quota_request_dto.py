import uuid

from pydantic import Field

from app.schemas.base import BaseDTO


# -- CreateQuotaRequest ("Add allocation" drawer) ----------------
class CreateQuotaRequestDTO(BaseDTO):
    train_id: uuid.UUID
    train_class: str = Field(min_length=1, max_length=5)
    general_pct: int = Field(ge=0, le=100)
    tatkal_pct: int = Field(ge=0, le=100)
    ladies_pct: int = Field(ge=0, le=100)
    premium_tatkal_pct: int = Field(ge=0, le=100)


# -- UpdateQuotaRequest ("Edit quota split" drawer) --------------
class UpdateQuotaRequestDTO(BaseDTO):
    general_pct: int = Field(ge=0, le=100)
    tatkal_pct: int = Field(ge=0, le=100)
    ladies_pct: int = Field(ge=0, le=100)
    premium_tatkal_pct: int = Field(ge=0, le=100)
