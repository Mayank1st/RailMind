from fastapi import APIRouter, Depends, File, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.common.common_service.common_service import CommonService
from app.api.deps import get_db
from app.core.response import ok

router = APIRouter(prefix="/common", tags=["Common"])

common_service = CommonService()


@router.get("/stations")
async def get_all_stations(db: AsyncSession = Depends(get_db)):
    data = await common_service.get_all_stations(db)
    return ok(data=data, message="All Stations Fetched Successfully.")


@router.post("/upload-supabase")
async def upload_data_into_supabase(file_byte: UploadFile = File(...)):
    data = await common_service.upload_data_into_supabase(file_byte)
    return ok(data=data, message="Data Uploaded Successfully.")
