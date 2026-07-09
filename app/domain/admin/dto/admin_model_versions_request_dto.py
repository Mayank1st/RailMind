from pydantic import Field

from app.schemas.base import BaseDTO


# -- ActivateModelVersionRequest ("Activate" / "Roll back to this") ---
class ActivateModelVersionRequestDTO(BaseDTO):
    version_label: str = Field(min_length=1, max_length=60)
