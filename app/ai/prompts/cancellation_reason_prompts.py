# ── Guard: the advisor decides, the LLM only rephrases (same contract as the
# waitlist/fare reason prompts) ────────────────────────────────────────────────
CANCELLATION_REASON_SYSTEM_INSTRUCTION = (
    "You are RailMind's ticket cancellation advisor. You are given a "
    "PRE-COMPUTED recommendation and the exact refund numbers behind it. "
    "Rephrase them into ONE short, friendly, trustworthy line in English "
    "telling the user whether to cancel or hold, and what it costs. "
    "STRICT RULES: use ONLY the numbers you are given; never invent amounts, "
    "percentages, deadlines or facts; never contradict the recommendation; "
    "no markdown; max 35 words."
)

# Keep the LLM on-message — a directive per recommendation so it can't drift.
CANCELLATION_RECOMMENDATION_DIRECTIVES = {
    "HOLD": "Keep the ticket — cancelling now gains nothing.",
    "MONITOR": "Unclear either way — hold and re-check closer to the journey.",
    "CANCEL_NOW": "Confirmation is unlikely — cancelling now is the sensible move.",
    "CANCEL_EARLY": (
        "Do NOT tell the user to cancel — you don't know their plans. Say that "
        "IF they decide to cancel, doing it before the deadline preserves the "
        "higher refund, which drops after it."
    ),
}


def cancellation_reason_prompt(
    recommendation: str,
    booking_status: str | None,
    refund_now: str,
    total_paid: str,
    next_drop_refund: str,
    cancel_by: str,
    confirm_pct: str,
    hours_to_departure: str,
) -> str:
    return (
        f"Recommendation: {recommendation}. "
        f"Directive: {CANCELLATION_RECOMMENDATION_DIRECTIVES.get(recommendation, '')} "
        f"Signals — booking status {booking_status}, "
        f"refund if cancelled now {refund_now} of {total_paid} paid, "
        f"refund after the next deadline {next_drop_refund}, "
        f"cancel-by deadline {cancel_by}, "
        f"waitlist confirmation chance {confirm_pct}, "
        f"{hours_to_departure} hours to departure. "
        f"Write the one-line advice."
    )
