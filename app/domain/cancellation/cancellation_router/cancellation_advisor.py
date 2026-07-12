from fastapi import APIRouter, Depends
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_db, get_redis, rate_limit
from app.core.advisor_flags import AdvisorKey, AdvisorState, get_advisor_state
from app.core.prediction_log_writer import log_prediction_async
from app.core.response import ok
from app.domain.cancellation.cancellation_service.cancellation_advisor_service import (
    CancellationAdvisorService,
)
from app.domain.cancellation.dto.cancellation_advisor_dto import (
    CancellationAdvisorResponseDTO,
)

router = APIRouter(prefix="/cancellation", tags=["Cancellation Advisor"])

cancellation_advisor_service = CancellationAdvisorService()


@router.get(
    "/advisor/{pnr}",
    dependencies=[Depends(rate_limit(limit=10, scope="cancellation_advisor"))],
)
async def get_cancellation_advice(
    pnr: str,
    explain: bool = False,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    redis: Redis = Depends(get_redis),
):
    state = await get_advisor_state(redis, AdvisorKey.CANCELLATION.value)
    waitlist_state = await get_advisor_state(redis, AdvisorKey.WAITLIST.value)
    data = await cancellation_advisor_service.advise(
        pnr=pnr,
        db=db,
        current_user_id=current_user["sub"],
        explain=explain,
        advisor_state=state,
        waitlist_advisor_state=waitlist_state,
    )

    # Prediction telemetry (best-effort, non-blocking) — only the WL branch is a
    # real prediction; the CNF refund ladder is deterministic arithmetic.
    waitlist = data.get("waitlist") or {}
    prob = waitlist.get("confirmation_probability")
    if prob is not None and data.get("recommendation"):
        log_prediction_async(
            advisor=AdvisorKey.CANCELLATION.value,
            input_summary=f"PNR {pnr} · {data.get('booking_status')}",
            predicted_label=data["recommendation"],
            predicted_confidence=prob,
            subject_ref=pnr,
            user_id=current_user.get("sub"),
            predicted_raw={
                "recommendation": data.get("recommendation"),
                "wl_bucket": waitlist.get("bucket"),
                "wl_probability": prob,
            },
        )

    return ok(
        data=CancellationAdvisorResponseDTO.model_validate(data),
        message="Cancellation advice generated successfully.",
        meta={"advisor_enabled": state != AdvisorState.OFF.value},
    )
