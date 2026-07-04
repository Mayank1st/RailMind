TAGLINE_SYSTEM_INSTRUCTION = (
    "You write ultra-short taglines for Indian railway destination cards on a "
    "travel homepage. Each tagline is 2-4 words, evocative, English, no "
    "punctuation at the end. Examples: 'Spiritual capital' for Varanasi, "
    "'Gateway of India' for Mumbai, 'Shatabdi Express' when the route is known "
    "for that train."
)

TAGLINE_PROMPT_TEMPLATE = (
    "Destinations (station name | typical train type):\n{destinations}\n\n"
    "Return STRICT JSON only — one object mapping each station name exactly as "
    'given to its tagline, e.g. {{"CHENNAI CENTRAL": "Shatabdi Express"}}. '
    "No markdown, no extra keys."
)


def trending_tagline_prompt(destinations: str) -> str:
    """destinations = newline-joined '- STATION NAME | TRAIN TYPE' lines."""
    return TAGLINE_PROMPT_TEMPLATE.format(destinations=destinations)
