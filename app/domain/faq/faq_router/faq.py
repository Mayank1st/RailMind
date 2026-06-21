from uuid import UUID

from fastapi import APIRouter, Depends
from fastapi_filter import FilterDepends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db
from app.core.pagination import Params, paginated
from app.core.response import created, ok
from app.domain.faq.dto.faq_filter_dto import FaqFilterDTO
from app.domain.faq.dto.faq_request_dto import FaqRequestDTO
from app.domain.faq.faq_service.faq_service import FaqService

router = APIRouter(prefix="/faq", tags=["Faq"])

faq_service = FaqService()


@router.post("/create")
async def create_faq(payload: FaqRequestDTO, db: AsyncSession = Depends(get_db)):
    data = await faq_service.create_faq(payload=payload, db=db)
    return created(data=data, message="FAQ created successfully.")


@router.get("/all")
async def get_all_faqs(
    faq_filter: FaqFilterDTO = FilterDepends(FaqFilterDTO),
    params: Params = Depends(),
    db: AsyncSession = Depends(get_db),
):
    page = await faq_service.list_faqs(db=db, faq_filter=faq_filter, params=params)
    return paginated(page, message="FAQs fetched successfully.")


@router.put("/update/{faq_id}")
async def update_faq(
    faq_id: UUID, payload: FaqRequestDTO, db: AsyncSession = Depends(get_db)
):
    data = await faq_service.update_faq(faq_id=faq_id, payload=payload, db=db)
    return ok(data=data, message="FAQ updated successfully.")


@router.delete("/delete/{faq_id}")
async def delete_faq(faq_id: UUID, db: AsyncSession = Depends(get_db)):
    await faq_service.delete_faq(faq_id=faq_id, db=db)
    return ok(message="FAQ deleted successfully.")
