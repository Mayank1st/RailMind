from fastapi import APIRouter
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db, get_current_user
from app.core.response import ok
from app.services.waitlist_predictor_service import WaitlistPredictorService

router = APIRouter(prefix="/waitlist")
waitlist_predictor_service = WaitlistPredictorService()


@router.get("/predictor/{pnr_number}")
async def get_waitlist_predictor_data(
    pnr_number: str,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):

    data = await waitlist_predictor_service.get_waitlist_predictor_data(
        pnr_number,
        db=db,
        current_user_id=current_user["sub"],
    )

    return ok(
        data=data,
        message=f"Data Fetched Successfully.",
    )
