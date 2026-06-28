from __future__ import annotations

import logging

from app.domain.waitlist.constants.waitlist_predictor import ERROR_CODE_PREDICTION
from app.integrations.gemini_client import gemini_client

logger = logging.getLogger(__name__)

# ── Guard: the predictor decides, Gemini only rephrases (planning doc §6.6) ─────
_SYSTEM_INSTRUCTION = (
    "You are RailMind's train waitlist advisor. You are given a PRE-COMPUTED "
    "confirmation outlook (bucket) and the exact signals behind it. Rephrase it "
    "into ONE short, friendly, trustworthy line in English telling the user how "
    "likely their waitlist is to confirm and what to do. STRICT RULES: "
    "use ONLY the numbers you are given; never invent probabilities, percentages, "
    "dates or facts; never contradict the bucket; no markdown; max 30 words."
)

# Keep Gemini on-message — a directive per bucket so it can't drift.
_DIRECTIVE = {
    "HIGH": "Strong chance of confirmation — the user can relax.",
    "MEDIUM": "Decent chance but no guarantee — keep a backup in mind.",
    "LOW": "Unlikely to confirm — the user should make an alternate plan.",
}


class WaitlistReasonService:
    """Level-3 — turns the deterministic bucket + signals into a natural-language
    line via Gemini. Gemini never computes anything: it only gets the numbers the
    backend already produced. Any failure (rate limit, error, empty) falls back to
    the templated reason already on the payload — the endpoint never blocks."""

    async def generate_reason(self, data: dict) -> str:
        fallback = data.get("reason", "")
        bucket = data.get("bucket", "")
        signals = data.get("signals", {}) or {}
        prob = data.get("confirmation_probability")

        prob_pct = f"{round(prob * 100)}%" if prob is not None else "unknown"
        cancel = signals.get("route_cancel_rate")
        cancel_pct = f"{round(cancel * 100)}%" if cancel is not None else "unknown"
        prompt = (
            f"Outlook: {bucket}. "
            f"Directive: {_DIRECTIVE.get(bucket, '')} "
            f"Signals — confirmation chance {prob_pct}, "
            f"waitlist type {signals.get('wl_type')}, "
            f"current position {signals.get('current_position')}, "
            f"{signals.get('days_to_journey')} days to journey, "
            f"route cancellation rate {cancel_pct}. "
            f"Write the one-line advice."
        )

        try:
            text = await gemini_client(
                prompt=prompt, system_instruction=_SYSTEM_INSTRUCTION
            )
        except Exception:
            logger.warning(
                "%s Gemini reason failed — using templated reason",
                ERROR_CODE_PREDICTION,
            )
            return fallback

        text = (text or "").strip()
        return text or fallback
