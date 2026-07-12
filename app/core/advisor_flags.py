from enum import Enum

from redis.asyncio import Redis

# Redis key holding an advisor's current state, e.g. "advisor:toggle:fare".
ADVISOR_TOGGLE_PREFIX = "advisor:toggle:"


class AdvisorState(str, Enum):
    OFF = "OFF"  # advisor disabled — return a neutral/disabled response
    FORCE_RULES = "FORCE_RULES"  # always serve the rule-based fallback, never ML
    ON = "ON"  # serve ML when available, else rules (default behaviour)


class AdvisorKey(str, Enum):
    FARE = "fare"
    WAITLIST = "waitlist"
    AUTOFILL = "autofill"
    CANCELLATION = "cancellation"


_VALID_STATES = {s.value for s in AdvisorState}


async def get_advisor_state(redis: Redis, advisor_key: str) -> str:
    """Current state for an advisor, read from the Redis mirror. Any miss/error
    (unset flag, Redis blip, bad value) falls back to ON so a control-plane
    problem can never silently disable a live advisor."""
    try:
        raw = await redis.get(f"{ADVISOR_TOGGLE_PREFIX}{advisor_key}")
        if raw in _VALID_STATES:
            return raw
    except Exception:
        pass
    return AdvisorState.ON.value


def model_allowed(state: str) -> bool:
    """True only when ML inference is permitted (state ON)."""
    return state == AdvisorState.ON.value


def is_disabled(state: str) -> bool:
    return state == AdvisorState.OFF.value
