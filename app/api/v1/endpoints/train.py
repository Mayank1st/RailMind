from fastapi import APIRouter
from app.core.response import APIResponse, created, ok


from app.services.train_service import TrainService
from app.schemas.train import SearchTrainDTO

router = APIRouter(prefix="/train", tags=["Train"])
train_service = TrainService()

@router.get("/search")
async def search_trains(payload:SearchTrainDTO):
    data = await train_service.search_trains(payload)
    return ok(data=data, message="Train Details Searched Successfully.")
