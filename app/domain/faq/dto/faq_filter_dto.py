from typing import Optional

from app.domain.faq.constants.faq import FaqCategory
from app.core.filters import BaseFilter
from app.db.models.faq import Faqs


# -- FaqFilter -----------------------------------------------
class FaqFilterDTO(BaseFilter):
    category: Optional[FaqCategory] = None
    order_by: Optional[list[str]] = ["-created_at"]

    class Constants(
        BaseFilter.Constants
    ):  # naming: ignore — fastapi-filter inner class
        model = Faqs
        search_model_fields = ["question", "answer"]
