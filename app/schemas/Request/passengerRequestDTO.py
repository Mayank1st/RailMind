from typing import Annotated, Optional
from pydantic import Field

from app.schemas.base import BaseDTO
from app.core.constants.auth_user import Gender
from app.core.constants.passenger import IdType
from app.core.constants.train import BerthType
from app.core.constants.auth_user import Gender


class CreatePassengerDTO(BaseDTO):
    full_name: Annotated[str, Field(examples=["Mayank Sharma"])]
    age: Annotated[int, Field(ge=1, le=120, examples=[25])]
    gender: Annotated[Gender, Field(examples=[Gender.MALE])]
    id_type: Annotated[str | None, Field(default=None)]
    id_number: Annotated[str | None, Field(default=None)]
    berth_preference: Annotated[BerthType, Field(default=BerthType.SIDE_LOWER)]
    is_primary: Annotated[bool, Field(default=False)]


class UpdatePassengerDTO(BaseDTO):
    full_name: Optional[str] = None
    age: Optional[int] = None
    gender: Optional[str] = None
    id_type: Optional[str] = None
    id_number: Optional[str] = None
    berth_preference: Optional[str] = None
    is_primary: Optional[bool] = None
