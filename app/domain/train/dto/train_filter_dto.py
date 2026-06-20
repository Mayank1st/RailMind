# Reference filter — copy this shape for any other resource.
#
# Query params auto-map to filters:
#   ?train_name__ilike=rajdhani        → WHERE train_name ILIKE '%rajdhani%'
#   ?train_type=SUPERFAST              → WHERE train_type = 'SUPERFAST'
#   ?train_number__in=12301,12302      → WHERE train_number IN (...)
#   ?search=mumbai                     → WHERE train_name ILIKE '%mumbai%' OR train_number ILIKE '%mumbai%'
#   ?order_by=-train_number,train_name → ORDER BY train_number DESC, train_name ASC

from typing import Optional

from app.core.filters import BaseFilter
from app.db.models.train import Trains


# -- TrainFilter ---------------------------------------------
class TrainFilterDTO(BaseFilter):
    # ── Filtering ──────────────────────────────────────────────────────────
    train_name__ilike: Optional[str] = None
    train_type: Optional[str] = None
    train_number: Optional[str] = None
    train_number__in: Optional[list[str]] = None

    class Constants(
        BaseFilter.Constants
    ):  # naming: ignore — fastapi-filter inner class
        model = Trains
        # columns the generic `search` param matches against
        search_model_fields = ["train_name", "train_number"]
