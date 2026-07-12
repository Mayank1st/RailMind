from __future__ import annotations

import logging

from app.ai.prompts.cancellation_reason_prompts import (
    CANCELLATION_REASON_SYSTEM_INSTRUCTION,
    cancellation_reason_prompt,
)
from app.domain.cancellation.constants.cancellation_advisor import ERROR_CODE_ADVISOR
from app.integrations.replicate_client import replicate_client
from app.integrations.replicate_models import MODEL1

logger = logging.getLogger(__name__)


class CancellationReasonService:
    """Level-3 — turns the deterministic recommendation + refund numbers into a
    natural-language line via the Replicate LLM (MODEL1). The LLM never computes
    anything: it only gets the numbers the backend already produced. Any failure
    (rate limit, error, empty) falls back to the templated reason already on the
    payload — the endpoint never blocks."""

    async def generate_reason(self, data: dict) -> str:
        fallback = data.get("reason", "")
        refund = data.get("refund") or {}
        waitlist = data.get("waitlist") or {}
        signals = data.get("signals") or {}

        prob = waitlist.get("confirmation_probability")
        confirm_pct = f"{round(prob * 100)}%" if prob is not None else "not applicable"

        next_step = self._next_drop_step(data.get("refund_ladder") or [])
        prompt = cancellation_reason_prompt(
            recommendation=data.get("recommendation") or "",
            booking_status=signals.get("booking_status"),
            refund_now=self._rupees(refund.get("refund_amount")),
            total_paid=self._rupees(refund.get("total_paid")),
            next_drop_refund=self._rupees(next_step.get("refund_amount")),
            cancel_by=next_step.get("cancel_by") or "none",
            confirm_pct=confirm_pct,
            hours_to_departure=str(signals.get("hours_to_departure") or "unknown"),
        )

        try:
            text = await replicate_client(
                prompt=prompt,
                model=MODEL1,
                system_prompt=CANCELLATION_REASON_SYSTEM_INSTRUCTION,
            )
        except Exception:
            logger.warning(
                "%s LLM reason failed — using templated reason",
                ERROR_CODE_ADVISOR,
            )
            return fallback

        text = (text or "").strip()
        return text or fallback

    # ── Helpers ───────────────────────────────────────────────────────────────

    @staticmethod
    def _rupees(amount: float | None) -> str:
        return f"Rs {amount:.0f}" if amount is not None else "unknown"

    @staticmethod
    def _next_drop_step(ladder: list[dict]) -> dict:
        """Upcoming refund drop: the lower amount and the deadline (end of the
        last window still paying the current amount) — mirrors the advisor."""
        if not ladder:
            return {}
        current_refund = ladder[0].get("refund_amount")
        deadline = ladder[0].get("cancel_by")
        for step in ladder[1:]:
            if step.get("refund_amount", 0) < current_refund:
                return {"cancel_by": deadline, "refund_amount": step["refund_amount"]}
            deadline = step.get("cancel_by")
        return {}
