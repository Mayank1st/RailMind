from typing import Annotated

from pydantic import BaseModel, Field

from app.core.constants.faq import FaqCategory


class FaqRequestDTO(BaseModel):
    question: Annotated[
        str, Field(min_length=1, max_length=255, examples=["How to file a TDR?"])
    ]
    answer: Annotated[
        str, Field(min_length=1, examples=["File it under Booking History > TDR."])
    ]
    category: FaqCategory = FaqCategory.GENERAL
    display_order: int = Field(default=0, ge=0)
