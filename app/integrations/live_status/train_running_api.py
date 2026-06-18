import logging
import re
from datetime import date, datetime, timezone
from typing import Any
from zoneinfo import ZoneInfo

import httpx

from app.config import settings

from .base import LiveStatusProvider
from .exceptions import (
    ProviderError,
    ProviderInvalidResponseError,
    ProviderInvalidTrainError,
    ProviderQuotaExceededError,
    ProviderTimeoutError,
    ProviderTrainNotRunningError,
)
from .schemas import LiveStatusResult, StationProgress

logger = logging.getLogger(__name__)

_IST = ZoneInfo("Asia/Kolkata")
_INVALID_HINTS = ("expired", "not found", "invalid", "does not exist", "no such")


class TrainRunningApiProvider(LiveStatusProvider):
    """Live running status via RapidAPI `train-running-api`.

    The upstream takes `start_day` (an integer day-offset: 0 = train started
    today, 1 = started yesterday, …), not a calendar date — so we derive it from
    the requested journey_date against *today in IST*.
    """

    provider_name = "train_running_api"
    PATH = "/api/LiveTrainApi/"

    async def fetch_live_status(
        self, train_number: str, journey_date: date
    ) -> LiveStatusResult:
        start_day = (datetime.now(_IST).date() - journey_date).days
        if start_day < 0:
            # Train departs in the future — there is no live status yet.
            raise ProviderTrainNotRunningError(
                "journey date is in the future; no live status available"
            )

        url = f"{settings.RAPIDAPI_LIVE_STATUS_BASE_URL}{self.PATH}"
        params = {"trainnumber": train_number, "start_day": start_day}
        headers = {
            "Content-Type": "application/json",
            "x-rapidapi-host": settings.RAPIDAPI_LIVE_STATUS_HOST,
            "x-rapidapi-key": settings.RAPIDAPI_LIVE_STATUS_KEY,
        }

        try:
            async with httpx.AsyncClient(
                timeout=settings.RAPIDAPI_LIVE_STATUS_TIMEOUT_SECONDS
            ) as client:
                resp = await client.get(url, params=params, headers=headers)
        except httpx.TimeoutException as e:
            raise ProviderTimeoutError(f"Provider timed out: {e}")
        except httpx.HTTPError as e:
            raise ProviderError(f"HTTP error: {e}")

        if resp.status_code == 429:
            raise ProviderQuotaExceededError("RapidAPI quota exceeded")
        if resp.status_code in (401, 403):
            raise ProviderError(f"Auth failed: {resp.status_code}")
        if resp.status_code >= 500:
            raise ProviderError(f"Upstream {resp.status_code}")

        try:
            raw = resp.json()
        except Exception as e:
            raise ProviderInvalidResponseError(f"Bad JSON: {e}")
        if not isinstance(raw, dict):
            raise ProviderInvalidResponseError("Response is not a JSON object")

        if raw.get("status") != "success":
            raise ProviderError(str(raw.get("message") or "provider error"))

        body = raw.get("data") or {}

        # Empty route ⇒ the train isn't trackable for this start_day. The upstream
        # uses status_message to say why ("already expired", etc.).
        if not body.get("stations"):
            msg = (body.get("status_message") or "").strip()
            if any(h in msg.lower() for h in _INVALID_HINTS):
                raise ProviderInvalidTrainError(msg or "train not found")
            raise ProviderTrainNotRunningError(msg or "no live status for this date")

        return self._normalize(body, train_number, journey_date)

    def _normalize(
        self, body: dict[str, Any], train_number: str, journey_date: date
    ) -> LiveStatusResult:
        route: list[StationProgress] = []
        for stop in body.get("stations", []):
            delay = self._parse_delay(stop.get("delay_status"))
            dep_actual = stop.get("departure_actual") or None
            route.append(
                StationProgress(
                    station_code=stop.get("code") or "",
                    station_name=(stop.get("name") or "").title(),
                    sequence_number=self._parse_int(stop.get("sequence")) or 0,
                    scheduled_arrival=stop.get("arrival_scheduled") or None,
                    actual_arrival=stop.get("arrival_actual") or None,
                    scheduled_departure=stop.get("departure_scheduled") or None,
                    actual_departure=dep_actual,
                    arrival_delay_minutes=delay,
                    departure_delay_minutes=delay,
                    distance_km=self._parse_float(stop.get("distance")),
                    halt_minutes=None,
                    platform_number=(
                        str(stop["platform"]) if stop.get("platform") else None
                    ),
                    day_number=None,
                    is_departed=bool(dep_actual),
                    is_current=bool(stop.get("is_current")),
                )
            )

        platform = body.get("platform_number")
        return LiveStatusResult(
            train_number=str(body.get("train_number") or train_number),
            train_name=body.get("train_name") or "",
            journey_date=body.get("train_start_date")
            or journey_date.strftime("%Y-%m-%d"),
            current_station_code=body.get("current_station_code") or None,
            current_station_name=body.get("current_station_name") or None,
            current_delay_minutes=self._parse_delay(body.get("delay")),
            last_reported_at=body.get("update_time")
            or body.get("status_as_of")
            or None,
            expected_platform=str(platform) if platform else None,
            route=route,
            raw_status_message=body.get("status_message")
            or body.get("status_as_of")
            or None,
            fetched_at=datetime.now(timezone.utc),
        )

    # ── Parsing helpers ───────────────────────────────────────────────────────

    @staticmethod
    def _parse_delay(value) -> int:
        """Parse 17, 'Delay  18m', '1h 5m', '00:14', 'Ontime' → integer minutes."""
        if value is None or value == "":
            return 0
        if isinstance(value, (int, float)):
            return int(value)
        s = str(value).strip()
        low = s.lower()
        if low in ("ontime", "on time", "right time", "rt", "-", "--", "0"):
            return 0
        if ":" in s:
            try:
                h, m = s.split(":")[:2]
                return int(h) * 60 + int(m)
            except ValueError:
                return 0
        h = re.search(r"(\d+)\s*h", low)
        m = re.search(r"(\d+)\s*m", low)
        if h or m:
            return (int(h.group(1)) * 60 if h else 0) + (int(m.group(1)) if m else 0)
        digits = "".join(ch for ch in s if ch.isdigit())
        return int(digits) if digits else 0

    @staticmethod
    def _parse_int(value):
        if value is None or value == "":
            return None
        try:
            return int(value)
        except (ValueError, TypeError):
            return None

    @staticmethod
    def _parse_float(value):
        if value is None or value == "":
            return None
        try:
            return float(value)
        except (ValueError, TypeError):
            return None
