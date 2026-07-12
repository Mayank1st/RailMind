from fastapi import APIRouter

from app.ai.pipelines import fare_predictor
from app.ai.pipelines import form_autofill
from app.ai.pipelines import nlp_search
from app.domain.cancellation.cancellation_router.cancellation_advisor import (
    router as cancellation_advisor_router,
)
from app.domain.waitlist.waitlist_router.waitlist_prediction import (
    router as waitlist_prediction_router,
)

router = APIRouter(prefix="/ai", tags=["AI"])
router.include_router(nlp_search.router)
router.include_router(form_autofill.router)
router.include_router(waitlist_prediction_router)
router.include_router(fare_predictor.router)
router.include_router(cancellation_advisor_router)
