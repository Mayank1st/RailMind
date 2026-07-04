import logging

from fastapi import APIRouter, Depends, Request
from fastapi_filter import FilterDepends
from sqlalchemy.ext.asyncio import AsyncSession
from app.api.deps import get_current_user, get_current_user_optional, get_db, get_redis
from app.core.response import APIResponse, created, ok
from app.core.pagination import Params, paginated


from app.domain.train.train_service.train_service import TrainService
from app.domain.train.dto.train_request_dto import (
    SearchTrainDTO,
    CheckSeatAvailabilityDTO,
)
from app.domain.train.dto.train_filter_dto import TrainFilterDTO
from app.tasks.search_history_tasks import (
    task_log_search_event,
    task_log_search_history,
)
from app.utils.helpers import build_session_hash

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/train", tags=["Train"])
train_service = TrainService()


@router.post("/search")
async def search_trains(
    payload: SearchTrainDTO,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: dict | None = Depends(get_current_user_optional),
):
    result = await train_service.search_trains(payload, db)
    if payload.toStationCode:
        try:
            task_log_search_event.delay(
                from_code=payload.fromStationCode.upper(),
                to_code=payload.toStationCode.upper(),
                user_id=current_user["sub"] if current_user else None,
                session_hash=(
                    None
                    if current_user
                    else build_session_hash(
                        request.client.host if request.client else "",
                        request.headers.get("user-agent", ""),
                    )
                ),
                journey_date=payload.journey_date.isoformat(),
                train_class=payload.train_class.value if payload.train_class else None,
                quota=payload.quota.value if payload.quota else None,
            )
            # Recent-searches feature — logged-in only (guests keep it in FE
            # localStorage).
            if current_user:
                task_log_search_history.delay(
                    user_id=current_user["sub"],
                    from_code=payload.fromStationCode.upper(),
                    to_code=payload.toStationCode.upper(),
                    journey_date=payload.journey_date.isoformat(),
                    train_class=(
                        payload.train_class.value if payload.train_class else None
                    ),
                    quota=payload.quota.value if payload.quota else None,
                )
        except Exception:
            logger.warning("failed to enqueue search logging", exc_info=True)

    return ok(
        data=result["items"],
        message="Train Details Fetched Successfully.",
        meta=result["meta"],
    )


# NOTE: must be registered before "/{train_number}" so "list" isn't captured
# as a train_number path param.
@router.get("/list")
async def list_trains(
    train_filter: TrainFilterDTO = FilterDepends(TrainFilterDTO),
    params: Params = Depends(),
    db: AsyncSession = Depends(get_db),
):
    page = await train_service.list_trains(db, train_filter, params)
    return paginated(page, message="Trains fetched successfully.")


@router.get("/{train_number}")
async def get_train_details_by_train_number(
    train_number: int, db: AsyncSession = Depends(get_db)
):
    data = await train_service.get_train_details_by_train_number(train_number, db)
    return ok(data=data, message="Train Details Fetched Successfully.")


@router.get("/{train_number}/schedule")
async def get_train_schedule(train_number: str, db: AsyncSession = Depends(get_db)):
    data = await train_service.get_train_schedule(train_number, db)
    return ok(data=data, message="Train Details Fetched Successfully.")


@router.post("/{train_number}/seat-availability")
async def get_seat_availability(
    train_number: str,
    payload: CheckSeatAvailabilityDTO,
    db: AsyncSession = Depends(get_db),
):
    data = await train_service.get_seat_availability(train_number, payload, db)
    return ok(data=data, message="Seat Availability Fetched Successfully.")


@router.get("/{train_number}/coach/seat-availability")
async def get_seat_availability_by_coach_number(
    train_number: str,
    payload: CheckSeatAvailabilityDTO,
    db: AsyncSession = Depends(get_db),
):
    data = await train_service.get_seat_availability_by_coach_number(
        train_number, payload, db
    )
    return ok(data=data, message="Seat Availability Fetched Successfully.")
