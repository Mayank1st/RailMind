from __future__ import annotations

import asyncio
from collections import Counter
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.services.booking_service import BookingService
from app.services.passenger_service import PassengerService

booking_service = BookingService()
passenger_service = PassengerService()

# ── Defaults ──────────────────────────────────────────────────────────────────
_DEFAULT_CLASS = "SL"
_DEFAULT_BERTH = "LB"
_DEFAULT_QUOTA = "GN"

# ── Confidence thresholds ─────────────────────────────────────────────────────
_HIGH = 5
_MEDIUM = 2


class AutoFillService:

    async def get_form_autofill_data(
        self,
        sourceStationCode: str,
        destinationStationCode: str,
        db: AsyncSession,
        current_user_id: str,
    ) -> dict:

        # ── Step 1: Fetch all user bookings ───────────────────────────────────
        booking_list = await booking_service.get_all_user_bookings(
            current_user_id, db=db
        )
        booking_ids = [b["booking_id"] for b in booking_list]

        # Fetch all booking details concurrently
        booking_details_list = await asyncio.gather(
            *[
                booking_service.get_booking_details_by_id(
                    booking_id=bid,
                    current_user_id=current_user_id,
                    db=db,
                )
                for bid in booking_ids
            ]
        )

        # Filter out None results
        all_bookings = [b for b in booking_details_list if b]

        # ── Step 2: Route-specific filter ─────────────────────────────────────
        route_bookings = [
            b
            for b in all_bookings
            if b.source_station_code == sourceStationCode
            and b.destination_station_code == destinationStationCode
        ]

        # ── Step 3: Decide source + preferred class ───────────────────────────
        if route_bookings:
            source = "route_history"
            history = route_bookings
        elif all_bookings:
            source = "general_history"
            history = all_bookings
        else:
            # No history at all — return defaults + passengers
            passengers = await self._get_passenger_suggestions(
                current_user_id, all_bookings, db
            )
            return {
                "preferred_class": _DEFAULT_CLASS,
                "preferred_berth": _DEFAULT_BERTH,
                "preferred_quota": _DEFAULT_QUOTA,
                "suggested_passengers": passengers,
                "confidence": "low",
                "source": "default",
                "based_on_bookings": 0,
            }

        total = len(history)

        # ── Step 4: Most common class ─────────────────────────────────────────
        train_classes = [b.train_class for b in history]
        preferred_class = Counter(train_classes).most_common(1)[0][0]

        # ── Step 5: Most common berth for that class ──────────────────────────
        # Look at passengers in bookings of preferred_class
        berths = []
        for b in history:
            if b.train_class == preferred_class and hasattr(b, "passengers"):
                for p in b.passengers or []:
                    if p.get("berth_preference"):
                        berths.append(p["berth_preference"])

        preferred_berth = (
            Counter(berths).most_common(1)[0][0] if berths else _DEFAULT_BERTH
        )

        # ── Step 6: Most common quota ─────────────────────────────────────────
        quotas = [b.quota for b in history if hasattr(b, "quota") and b.quota]
        preferred_quota = (
            Counter(quotas).most_common(1)[0][0] if quotas else _DEFAULT_QUOTA
        )

        # ── Step 7: Passenger suggestions ────────────────────────────────────
        passengers = await self._get_passenger_suggestions(
            current_user_id, all_bookings, db
        )

        # ── Step 8: Confidence score ──────────────────────────────────────────
        if total >= _HIGH:
            confidence = "high"
        elif total >= _MEDIUM:
            confidence = "medium"
        else:
            confidence = "low"

        return {
            "preferred_class": preferred_class,
            "preferred_berth": preferred_berth,
            "preferred_quota": preferred_quota,
            "suggested_passengers": passengers,
            "confidence": confidence,
            "source": source,
            "based_on_bookings": total,
        }

    # ── Passenger suggestions ─────────────────────────────────────────────────

    async def _get_passenger_suggestions(
        self,
        current_user_id: str,
        all_bookings: list,
        db: AsyncSession,
        limit: int = 4,
    ) -> list[dict]:
        passenger_counter: Counter = Counter()
        for b in all_bookings:
            if hasattr(b, "passengers"):
                for p in b.passengers or []:
                    pid = (
                        p.get("passenger_id")
                        if isinstance(p, dict)
                        else getattr(p, "passenger_id", None)
                    )
                    if pid:
                        passenger_counter[str(pid)] += 1

        try:
            response = await passenger_service.passenger_list(current_user_id, db=db)
            passengers = response.passengers  # ← .passengers se list nikalo
        except Exception:
            return []  # no saved passengers — return empty

        # Pydantic models hain — attribute access, .get() nahi
        enriched = []
        for p in passengers:
            pid = str(p.id)  # ← .get("id") nahi, .id
            enriched.append(
                {
                    "id": str(p.id),
                    "full_name": p.full_name,
                    "age": p.age,
                    "gender": p.gender,
                    "berth_preference": p.berth_preference,
                    "is_primary": p.is_primary,
                    "booking_count": passenger_counter.get(pid, 0),
                }
            )

        enriched.sort(key=lambda x: x["booking_count"], reverse=True)
        return enriched[:limit]
