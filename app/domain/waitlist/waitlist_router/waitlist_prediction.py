from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_db, rate_limit
from app.core.response import ok
from app.domain.waitlist.constants.waitlist_predictor import CONFIDENCE_THRESHOLD
from app.domain.waitlist.dto.waitlist_prediction_dto import (
    WaitlistPredictionResponseDTO,
)
from app.domain.waitlist.waitlist_service.waitlist_prediction_service import (
    WaitlistPredictionService,
)

router = APIRouter(prefix="/waitlist", tags=["Waitlist Prediction"])

waitlist_prediction_service = WaitlistPredictionService()


@router.get(
    "/prediction/{pnr}",
    dependencies=[Depends(rate_limit(limit=10, scope="waitlist_prediction"))],
)
async def get_waitlist_prediction(
    pnr: str,
    explain: bool = False,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    data = await waitlist_prediction_service.predict(
        pnr=pnr, db=db, current_user_id=current_user["sub"], explain=explain
    )
    return ok(
        data=WaitlistPredictionResponseDTO.model_validate(data),
        message="Waitlist prediction generated successfully.",
        meta={"confidence_threshold": CONFIDENCE_THRESHOLD},
    )
