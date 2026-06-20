from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db, get_current_user
from app.core.response import ok

from app.domain.pnr.pnr_service.pnr_service import PnrService

pnr_service = PnrService()


router = APIRouter(prefix="/pnr", tags=["PNR"])


@router.get("/{pnr_number}/user")
async def get_pnr_status_of_current_user(
    pnr_number: str,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    data = await pnr_service.get_pnr_status_of_current_user(
        pnr_number,
        current_user_id=current_user["sub"],
        db=db,
    )
    return ok(
        data=data,
        message=f"PNR Details fetched successfully.",
    )


@router.get("/{pnr_number}")
async def get_pnr_status(
    pnr_number: str,
    db: AsyncSession = Depends(get_db),
):
    data = await pnr_service.get_pnr_status(
        pnr_number,
        db=db,
    )
    return ok(
        data=data,
        message=f"PNR Details fetched successfully.",
    )


@router.get("/get-recently-checked-pnr")
async def get_recently_checked_pnr(db: AsyncSession = Depends(get_db)):
    # This route requires model training to identify recently checked PNRs
    pass
