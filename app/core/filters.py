# Filtering / sorting / search base
#
# Built on `fastapi-filter`. Subclass `BaseFilter` per model, declare the
# filterable fields (with operator suffixes), and point `Constants.model` at
# the SQLAlchemy model. The route does:
#
#     query = my_filter.filter(query)   # WHERE  (field filters + search)
#     query = my_filter.sort(query)     # ORDER BY (?order_by=-col,col2)
#
# Common operator suffixes: __ilike __like __gt __gte __lt __lte __in __not __isnull
# No suffix = exact match.

from typing import Optional

from fastapi_filter.contrib.sqlalchemy import Filter


class BaseFilter(Filter):
    """
    Common, generic filter fields shared by every resource filter.

    - `search`   : multi-column case-insensitive search. Each subclass must list
                   the columns it searches via `Constants.search_model_fields`.
    - `order_by` : sorting, e.g. ?order_by=-created_at,train_name
                   (prefix `-` = descending).

    Subclass example:
        class TrainFilterDTO(BaseFilter):
            train_name__ilike: Optional[str] = None
            class Constants(BaseFilter.Constants):
                model = Trains
                search_model_fields = ["train_name", "train_number"]
    """

    search: Optional[str] = None
    order_by: Optional[list[str]] = None
