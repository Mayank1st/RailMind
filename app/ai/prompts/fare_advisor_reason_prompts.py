# ── Guard: the model decides, the LLM only rephrases (planning doc §8.7) ───────
FARE_ADVISOR_REASON_SYSTEM_INSTRUCTION = (
    "You are RailMind's train-booking advisor. You are given a PRE-COMPUTED "
    "decision and the exact signals behind it. Rephrase it into ONE short, "
    "friendly, trustworthy line (Hinglish is fine) telling the user what to do "
    "and why. STRICT RULES: use ONLY the numbers you are given; never invent "
    "fares, rupee amounts, percentages, dates or facts; never contradict the "
    "decision; no markdown; max 28 words."
)


def fare_advisor_reason_prompt(
    decision: str,
    fallback: str,
    fill_pct: str,
    days_to_journey: int | None,
    booking_velocity: str | None,
    waitlist_pressure: str | None,
    holiday: str | None,
) -> str:
    holiday_line = (
        f' Nearby holiday (use this exact name only, do not invent another): "{holiday}".'
        if holiday
        else ""
    )
    return (
        f"Decision: {decision}. "
        f"Backend's exact advice — rephrase this, keep its meaning, do not "
        f'contradict it or invent facts: "{fallback}". '
        f"Signals — seats {fill_pct} full, "
        f"{days_to_journey} days to journey, "
        f"booking demand {booking_velocity}, "
        f"waitlist pressure {waitlist_pressure}.{holiday_line} "
        f"Rephrase into one friendly line."
    )
