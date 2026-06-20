from uuid import UUID

from app.domain.faq.constants.faq import FaqCategory
from app.schemas.base import BaseDTO


# -- FaqResponse ---------------------------------------------
class FaqResponseDTO(BaseDTO):
    id: UUID
    question: str
    answer: str
    category: FaqCategory
    display_order: int
