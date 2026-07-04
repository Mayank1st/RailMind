"""Nearby-holiday lookup for the Fare Advisor reason — DISPLAY ONLY.

Pure, offline, deterministic (the `holidays` package ships its data locally — no
network, no API key). This feeds ONLY the reason/signals so a user sees the
concrete "why" (e.g. "Diwali"). It is NOT a decision or model input — the model's
`is_festival_season` feature already makes the decision season-aware; adding the
holiday to the decision logic too would double-count. Keep this reason-only.

Any failure (package missing, bad data) returns None — the advisor must never
crash on a display nicety.
"""

from __future__ import annotations

from datetime import date, timedelta

try:  # optional dependency — a missing package must degrade to None, not 500
    import holidays
except ImportError:  # pragma: no cover
    holidays = None

from app.domain.fare.constants.fare_advisor import (
    HOLIDAY_LOOKAHEAD_DAYS,
    HOLIDAY_LOOKBEHIND_DAYS,
)


def get_nearby_holiday(journey_date: date) -> dict | None:
    """Nearest Indian national holiday around `journey_date`, or None.

    Returns {"name", "holiday_date", "days_from_journey"}. Window is asymmetric —
    lookbehind is small (people travel before a festival, not after). Scans from
    the journey outward so the closest holiday wins.
    """
    if holidays is None:
        return None
    try:
        years = {
            journey_date.year,
            (journey_date + timedelta(days=HOLIDAY_LOOKAHEAD_DAYS)).year,
            (journey_date - timedelta(days=HOLIDAY_LOOKBEHIND_DAYS)).year,
        }
        in_holidays = holidays.India(years=list(years))
        # closest holiday wins; on a tie prefer the one ahead (festival ahead = the
        # one people are travelling for).
        offsets = sorted(
            range(-HOLIDAY_LOOKBEHIND_DAYS, HOLIDAY_LOOKAHEAD_DAYS + 1),
            key=lambda o: (abs(o), -o),
        )
        for offset in offsets:
            day = journey_date + timedelta(days=offset)
            if day in in_holidays:
                return {
                    "name": in_holidays[day],
                    "holiday_date": day.isoformat(),
                    "days_from_journey": offset,
                }
        return None
    except Exception:
        return None


def nearby_holiday_name(journey_date: date) -> str | None:
    """Just the holiday name (what the reason/signals need), or None."""
    holiday = get_nearby_holiday(journey_date)
    return holiday["name"] if holiday else None
