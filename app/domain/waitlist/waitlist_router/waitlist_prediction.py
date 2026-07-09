from fastapi import APIRouter, Depends
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_db, get_redis, rate_limit
from app.core.advisor_flags import AdvisorKey, AdvisorState, get_advisor_state
from app.core.prediction_log_writer import log_prediction_async
from app.core.response import ok
from app.domain.waitlist.constants.waitlist_predictor import CONFIDENCE_THRESHOLD
from app.domain.waitlist.dto.waitlist_prediction_dto import (
    WaitlistPredictionResponseDTO,
)
from app.domain.waitlist.waitlist_service.waitlist_prediction_service import (
    WaitlistPredictionService,
)

router = APIRouter(prefix="/waitlist", tags=["Waitlist Prediction"])

waitlist_prediction_service = WaitlistPredictionService()


@router.get(
    "/prediction/{pnr}",
    dependencies=[Depends(rate_limit(limit=10, scope="waitlist_prediction"))],
)
async def get_waitlist_prediction(
    pnr: str,
    explain: bool = False,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    redis: Redis = Depends(get_redis),
):
    state = await get_advisor_state(redis, AdvisorKey.WAITLIST.value)
    data = await waitlist_prediction_service.predict(
        pnr=pnr,
        db=db,
        current_user_id=current_user["sub"],
        explain=explain,
        advisor_state=state,
    )

    # Prediction telemetry (best-effort, non-blocking) — only real predictions.
    prob = data.get("confirmation_probability")
    if prob is not None:
        signals = data.get("signals") or {}
        wl_type = signals.get("wl_type") or ""
        position = signals.get("current_position")
        suffix = f" · {wl_type}{position}" if wl_type and position is not None else ""
        log_prediction_async(
            advisor=AdvisorKey.WAITLIST.value,
            input_summary=f"PNR {pnr}{suffix}",
            predicted_label=f"Confirm {round(prob * 100)}%",
            predicted_confidence=prob,
            subject_ref=pnr,
            user_id=current_user.get("sub"),
            predicted_raw={"bucket": data.get("bucket"), "probability": prob},
        )

    return ok(
        data=WaitlistPredictionResponseDTO.model_validate(data),
        message="Waitlist prediction generated successfully.",
        meta={
            "confidence_threshold": CONFIDENCE_THRESHOLD,
            "advisor_enabled": state != AdvisorState.OFF.value,
        },
    )
