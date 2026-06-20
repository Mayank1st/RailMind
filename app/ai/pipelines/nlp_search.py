from fastapi import APIRouter
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db, get_current_user
from app.core.response import ok
from app.domain.nlp_search.nlp_search_service.nlp_search_service import NlpSearchService
from app.domain.nlp_search.dto.nlp_search_dto import GetNLPSearchDTO

router = APIRouter(prefix="/nlp")
nlp_search_service = NlpSearchService()


@router.post("/search")
async def get_nlp_search(
    plain_text: GetNLPSearchDTO,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    data = await nlp_search_service.get_nlp_search(
        plain_text,
        current_user_id=current_user["sub"],
        db=db,
    )
    return ok(
        data=data,
        message=f"Data Fetched Successfully.",
    )
