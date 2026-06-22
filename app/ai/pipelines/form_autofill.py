import logging
from datetime import date

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db, get_current_user
from app.config import settings
from app.core.response import ok
from app.domain.autofill.autofill_service.autofill_service import AutoFillService
from app.domain.autofill.autofill_service.autofill_rules_service import (
    AutofillRulesService,
)
from app.domain.autofill.autofill_service.autofill_model_service import (
    AutofillModelService,
)
from app.domain.autofill.constants.autofill import MODEL_MIN_BOOKINGS
from app.domain.autofill.dto.autofill_dto import SmartAutofillResponseDTO

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/form")
auto_fill_service = AutoFillService()
autofill_rules_service = AutofillRulesService()
autofill_model_service = AutofillModelService()


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


@router.get("/smart-autofill")
async def get_smart_autofill_data(
    source_station_code: str,
    destination_station_code: str,
    train_number: str | None = None,
    journey_date: date | None = None,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    user_id = current_user["sub"]
    favourite_train = None
    try:
        favourite_train = await autofill_rules_service.favourite_train(
            db, user_id, source_station_code, destination_station_code
        )
    except Exception:
        logger.exception("RM-AI-001 favourite_train lookup failed")
        await db.rollback()

    booking_count = await autofill_rules_service.count_user_bookings(db, user_id)

    if not train_number:
        data = autofill_rules_service.empty_suggestion(booking_count)
    elif booking_count > MODEL_MIN_BOOKINGS and autofill_model_service.is_available():
        data = await autofill_model_service.suggest_autofill(
            db=db,
            user_id=user_id,
            train_number=train_number,
            source_station_code=source_station_code,
            destination_station_code=destination_station_code,
            journey_date=journey_date,
        )
    else:
        data = await autofill_rules_service.suggest_autofill(
            db=db,
            user_id=user_id,
            train_number=train_number,
            source_station_code=source_station_code,
            destination_station_code=destination_station_code,
        )

    data["favourite_train"] = favourite_train

    return ok(
        data=SmartAutofillResponseDTO.model_validate(data),
        message="Autofill suggestions generated successfully.",
        meta={"confidence_threshold": settings.AI_CONFIDENCE_THRESHOLD},
    )
