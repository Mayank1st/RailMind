from typing import Optional

from app.core.constants.faq import FaqCategory
from app.core.filters import BaseFilter
from app.db.models.faq import Faqs


class FaqFilter(BaseFilter):
    category: Optional[FaqCategory] = None
    order_by: Optional[list[str]] = ["-created_at"]

    class Constants(BaseFilter.Constants):
        model = Faqs
        search_model_fields = ["question", "answer"]
