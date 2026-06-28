from __future__ import annotations

import logging

from app.domain.fare.constants.fare_advisor import ERROR_CODE_ADVISOR
from app.integrations.gemini_client import gemini_client

logger = logging.getLogger(__name__)

# ── Guard: the model decides, Gemini only rephrases (planning doc §8.7) ────────
_SYSTEM_INSTRUCTION = (
    "You are RailMind's train-booking advisor. You are given a PRE-COMPUTED "
    "decision and the exact signals behind it. Rephrase it into ONE short, "
    "friendly, trustworthy line (Hinglish is fine) telling the user what to do "
    "and why. STRICT RULES: use ONLY the numbers you are given; never invent "
    "fares, rupee amounts, percentages, dates or facts; never contradict the "
    "decision; no markdown; max 28 words."
)


class FareAdvisorReasonService:
    """Level-3 — turns the deterministic decision + signals into a natural-language
    nudge via Gemini. Gemini never computes anything: it only gets the numbers the
    backend already produced. Any failure (rate limit, error, empty) falls back to
    the templated reason already on the payload — the endpoint never blocks."""

    async def generate_reason(self, data: dict) -> str:
        fallback = data.get("reason", "")
        decision = data.get("decision", "")
        signals = data.get("signals", {}) or {}

        fill = signals.get("fill_rate")
        fill_pct = f"{round(fill * 100)}%" if fill is not None else "unknown"
        # Rephrase the backend's already-correct sentence (so Gemini can't drift back
        # into a wrong framing — e.g. "book to avoid WL" on a sold-out class).
        prompt = (
            f"Decision: {decision}. "
            f"Backend's exact advice — rephrase this, keep its meaning, do not "
            f'contradict it or invent facts: "{fallback}". '
            f"Signals — seats {fill_pct} full, "
            f"{signals.get('days_to_journey')} days to journey, "
            f"booking demand {signals.get('booking_velocity')}, "
            f"waitlist pressure {signals.get('waitlist_pressure')}. "
            f"Rephrase into one friendly line."
        )

        try:
            text = await gemini_client(
                prompt=prompt, system_instruction=_SYSTEM_INSTRUCTION
            )
        except Exception:
            logger.warning(
                "%s Gemini reason failed — using templated reason", ERROR_CODE_ADVISOR
            )
            return fallback

        text = (text or "").strip()
        return text or fallback
