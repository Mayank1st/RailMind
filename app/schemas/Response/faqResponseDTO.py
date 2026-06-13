from uuid import UUID

from app.core.constants.faq import FaqCategory
from app.schemas.base import BaseDTO


class FaqResponseDTO(BaseDTO):
    id: UUID
    question: str
    answer: str
    category: FaqCategory
    display_order: int
