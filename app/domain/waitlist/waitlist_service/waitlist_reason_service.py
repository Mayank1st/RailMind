from __future__ import annotations

import logging

from app.ai.prompts.waitlist_reason_prompts import (
    WAITLIST_REASON_SYSTEM_INSTRUCTION,
    waitlist_reason_prompt,
)
from app.domain.waitlist.constants.waitlist_predictor import ERROR_CODE_PREDICTION
from app.integrations.replicate_client import replicate_client
from app.integrations.replicate_models import MODEL1

logger = logging.getLogger(__name__)


class WaitlistReasonService:
    """Level-3 — turns the deterministic bucket + signals into a natural-language
    line via the Replicate LLM (MODEL1). The LLM never computes anything: it only
    gets the numbers the backend already produced. Any failure (rate limit, error,
    empty) falls back to the templated reason already on the payload — the
    endpoint never blocks."""

    async def generate_reason(self, data: dict) -> str:
        fallback = data.get("reason", "")
        bucket = data.get("bucket", "")
        signals = data.get("signals", {}) or {}
        prob = data.get("confirmation_probability")

        prob_pct = f"{round(prob * 100)}%" if prob is not None else "unknown"
        cancel = signals.get("route_cancel_rate")
        cancel_pct = f"{round(cancel * 100)}%" if cancel is not None else "unknown"
        prompt = waitlist_reason_prompt(
            bucket=bucket,
            prob_pct=prob_pct,
            wl_type=signals.get("wl_type"),
            current_position=signals.get("current_position"),
            days_to_journey=signals.get("days_to_journey"),
            cancel_pct=cancel_pct,
        )

        try:
            text = await replicate_client(
                prompt=prompt,
                model=MODEL1,
                system_prompt=WAITLIST_REASON_SYSTEM_INSTRUCTION,
            )
        except Exception:
            logger.warning(
                "%s LLM reason failed — using templated reason",
                ERROR_CODE_PREDICTION,
            )
            return fallback

        text = (text or "").strip()
        return text or fallback
