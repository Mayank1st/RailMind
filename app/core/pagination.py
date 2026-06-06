from fastapi import Query
from fastapi_pagination import Params as _Params
from fastapi_pagination.bases import AbstractPage

from app.core.response import APIResponse, ok

# ─── Defaults ─────────────────────────────────────────────────────────────────

DEFAULT_PAGE_SIZE = 10
BOOKING_PAGE_SIZE = 5  # bookings list shows 5 per page
MAX_PAGE_SIZE = 100


# ─── Query params (?page=&size=) ──────────────────────────────────────────────


class Params(_Params):
    """Project-wide pagination params. Inject with `Depends()`."""

    size: int = Query(
        DEFAULT_PAGE_SIZE, ge=1, le=MAX_PAGE_SIZE, description="Records per page"
    )


class BookingParams(_Params):
    """Bookings list — defaults to 5 records per page."""

    size: int = Query(
        BOOKING_PAGE_SIZE, ge=1, le=MAX_PAGE_SIZE, description="Records per page"
    )


# ─── Envelope adapter ─────────────────────────────────────────────────────────


def paginated(page: AbstractPage, *, message: str = "Success") -> APIResponse:
    """Wrap a fastapi-pagination `Page` into the `APIResponse` envelope."""
    return ok(
        data=page.items,
        message=message,
        meta={
            "total": page.total,
            "page": page.page,
            "size": page.size,
            "pages": page.pages,
        },
    )
