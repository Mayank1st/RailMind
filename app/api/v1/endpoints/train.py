from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from app.api.deps import get_current_user, get_db, get_redis
from app.core.response import APIResponse, created, ok


from app.services.train_service import TrainService
from app.schemas.train import SearchTrainDTO, CheckSeatAvailabilityDTO

router = APIRouter(prefix="/train", tags=["Train"])
train_service = TrainService()


@router.post("/search")
async def search_trains(payload: SearchTrainDTO, db: AsyncSession = Depends(get_db)):
    data = await train_service.search_trains(payload, db)
    return ok(data=data, message="Train Details Fetched Successfully.")


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
