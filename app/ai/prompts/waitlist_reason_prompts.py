# ── Guard: the predictor decides, the LLM only rephrases (planning doc §6.6) ────
WAITLIST_REASON_SYSTEM_INSTRUCTION = (
    "You are RailMind's train waitlist advisor. You are given a PRE-COMPUTED "
    "confirmation outlook (bucket) and the exact signals behind it. Rephrase it "
    "into ONE short, friendly, trustworthy line in English telling the user how "
    "likely their waitlist is to confirm and what to do. STRICT RULES: "
    "use ONLY the numbers you are given; never invent probabilities, percentages, "
    "dates or facts; never contradict the bucket; no markdown; max 30 words."
)

# Keep the LLM on-message — a directive per bucket so it can't drift.
WAITLIST_BUCKET_DIRECTIVES = {
    "HIGH": "Strong chance of confirmation — the user can relax.",
    "MEDIUM": "Decent chance but no guarantee — keep a backup in mind.",
    "LOW": "Unlikely to confirm — the user should make an alternate plan.",
}


def waitlist_reason_prompt(
    bucket: str,
    prob_pct: str,
    wl_type: str | None,
    current_position: int | None,
    days_to_journey: int | None,
    cancel_pct: str,
) -> str:
    return (
        f"Outlook: {bucket}. "
        f"Directive: {WAITLIST_BUCKET_DIRECTIVES.get(bucket, '')} "
        f"Signals — confirmation chance {prob_pct}, "
        f"waitlist type {wl_type}, "
        f"current position {current_position}, "
        f"{days_to_journey} days to journey, "
        f"route cancellation rate {cancel_pct}. "
        f"Write the one-line advice."
    )
