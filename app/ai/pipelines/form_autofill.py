from fastapi import APIRouter
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db, get_current_user
from app.core.response import ok
from app.domain.autofill.autofill_service.autofill_service import AutoFillService

router = APIRouter(prefix="/form")
auto_fill_service = AutoFillService()


@router.get("/autofill")
async def get_form_autofill_data(
    sourceStationCode: str,
    destinationStationCode: str,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):

    data = await auto_fill_service.get_form_autofill_data(
        sourceStationCode,
        destinationStationCode,
        db=db,
        current_user_id=current_user["sub"],
    )

    return ok(
        data=data,
        message=f"Data Fetched Successfully.",
    )
