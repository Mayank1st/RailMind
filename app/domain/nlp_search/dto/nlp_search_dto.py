from typing import Annotated, Optional
from pydantic import Field

from app.schemas.base import BaseDTO


# -- GetNLPSearch --------------------------------------------
class GetNLPSearchDTO(BaseDTO):
    plain_text: Annotated[str, Field(examples=["Delhi to Mumbai tomorrow AC"])]
