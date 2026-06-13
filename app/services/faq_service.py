from uuid import UUID

from fastapi import status
from fastapi_pagination import Params
from fastapi_pagination.ext.sqlalchemy import apaginate
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import RailMindException
from app.db.models.faq import Faqs
from app.schemas.Request.faqFilterDTO import FaqFilter
from app.schemas.Request.faqRequestDTO import FaqRequestDTO
from app.schemas.Response.faqResponseDTO import FaqResponseDTO


class FaqService:

    async def create_faq(
        self, payload: FaqRequestDTO, db: AsyncSession
    ) -> FaqResponseDTO:
        await self._ensure_question_unique(payload.question, db)

        new_faq = Faqs(
            question=payload.question,
            answer=payload.answer,
            category=payload.category,
            display_order=payload.display_order,
        )
        db.add(new_faq)
        await db.flush()
        await db.refresh(new_faq)

        return FaqResponseDTO.model_validate(new_faq)

    async def list_faqs(self, db: AsyncSession, faq_filter: FaqFilter, params: Params):
        """Paginated FAQ list with category filter, free-text search and sorting.
        Reuses the generic filter+sort+paginate pattern (see train_service)."""
        query = select(Faqs)
        query = faq_filter.filter(query)  # WHERE: category + search
        query = faq_filter.sort(query)  # ORDER BY: ?order_by= (default -created_at)

        return await apaginate(
            db,
            query,
            params,
            transformer=lambda rows: [
                FaqResponseDTO.model_validate(faq) for faq in rows
            ],
        )

    async def update_faq(
        self, faq_id: UUID, payload: FaqRequestDTO, db: AsyncSession
    ) -> FaqResponseDTO:
        faq = await self._get_faq_or_404(faq_id, db)
        await self._ensure_question_unique(payload.question, db, exclude_id=faq_id)

        faq.question = payload.question
        faq.answer = payload.answer
        faq.category = payload.category
        faq.display_order = payload.display_order
        await db.flush()
        await db.refresh(faq)

        return FaqResponseDTO.model_validate(faq)

    async def delete_faq(self, faq_id: UUID, db: AsyncSession) -> None:
        faq = await self._get_faq_or_404(faq_id, db)
        await db.delete(faq)
        await db.flush()

    # ── helpers ───────────────────────────────────────────────────────────────

    async def _get_faq_or_404(self, faq_id: UUID, db: AsyncSession) -> Faqs:
        result = await db.execute(select(Faqs).where(Faqs.id == faq_id))
        faq = result.scalar_one_or_none()
        if faq is None:
            raise RailMindException(
                code="RM-FAQ-002",
                message="FAQ not found",
                status_code=status.HTTP_404_NOT_FOUND,
            )
        return faq

    async def _ensure_question_unique(
        self, question: str, db: AsyncSession, exclude_id: UUID | None = None
    ) -> None:
        stmt = select(Faqs.id).where(Faqs.question == question)
        if exclude_id is not None:
            stmt = stmt.where(Faqs.id != exclude_id)
        if (await db.execute(stmt)).scalar_one_or_none() is not None:
            raise RailMindException(
                code="RM-FAQ-001",
                message="FAQ with this question already exists",
                status_code=status.HTTP_409_CONFLICT,
            )
