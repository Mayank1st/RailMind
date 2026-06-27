from fastapi import APIRouter
from app.ai.pipelines import nlp_search
from app.ai.pipelines import form_autofill
from app.ai.pipelines import waitlist_predictor
from app.ai.pipelines import fare_predictor

router = APIRouter(prefix="/ai", tags=["AI"])
router.include_router(nlp_search.router)
router.include_router(form_autofill.router)
router.include_router(waitlist_predictor.router)
router.include_router(fare_predictor.router)
