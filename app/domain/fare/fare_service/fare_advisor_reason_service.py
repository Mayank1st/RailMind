from __future__ import annotations

import logging

from app.ai.prompts.fare_advisor_reason_prompts import (
    FARE_ADVISOR_REASON_SYSTEM_INSTRUCTION,
    fare_advisor_reason_prompt,
)
from app.domain.fare.constants.fare_advisor import ERROR_CODE_ADVISOR
from app.integrations.replicate_client import replicate_client
from app.integrations.replicate_models import MODEL1

logger = logging.getLogger(__name__)


class FareAdvisorReasonService:
    """Level-3 — turns the deterministic decision + signals into a natural-language
    nudge via the Replicate LLM (MODEL1). The LLM never computes anything: it only
    gets the numbers the backend already produced. Any failure (rate limit, error,
    empty) falls back to the templated reason already on the payload — the
    endpoint never blocks."""

    async def generate_reason(self, data: dict) -> str:
        fallback = data.get("reason", "")
        decision = data.get("decision", "")
        signals = data.get("signals", {}) or {}

        fill = signals.get("fill_rate")
        fill_pct = f"{round(fill * 100)}%" if fill is not None else "unknown"
        prompt = fare_advisor_reason_prompt(
            decision=decision,
            fallback=fallback,
            fill_pct=fill_pct,
            days_to_journey=signals.get("days_to_journey"),
            booking_velocity=signals.get("booking_velocity"),
            waitlist_pressure=signals.get("waitlist_pressure"),
            holiday=signals.get("nearby_holiday"),
        )

        try:
            text = await replicate_client(
                prompt=prompt,
                model=MODEL1,
                system_prompt=FARE_ADVISOR_REASON_SYSTEM_INSTRUCTION,
            )
        except Exception:
            logger.warning(
                "%s LLM reason failed — using templated reason", ERROR_CODE_ADVISOR
            )
            return fallback

        text = (text or "").strip()
        return text or fallback
