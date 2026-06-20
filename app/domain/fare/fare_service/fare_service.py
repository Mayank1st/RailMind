import json
from datetime import date

from fastapi import status
from redis.asyncio import Redis
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.auth.constants.auth_user import CACHE_TTL_FARE
from app.core.exceptions import RailMindException
from app.core.fare_calculator import FareBreakdown, FareCalculator
from app.db.models.booking import FareRules
from app.domain.fare.dto.fare_dto import (
    FareBreakdownDTO,
    FareEnquiryRequestDTO,
    FareEnquiryResponseDTO,
)
from app.domain.train.dto.train_request_dto import ValidateJourneyDTO
from app.domain.train.train_service.train_service import TrainService

_CLASS_ORDER = ["2S", "SL", "CC", "3E", "3A", "FC", "2A", "1A"]


class FareEnquiryService:
    async def get_fare_enquiry(
        self,
        payload: FareEnquiryRequestDTO,
        db: AsyncSession,
        redis: Redis,
    ) -> tuple[dict, bool]:
        """Returns (response_data, served_from_cache)."""

        # ── 1. Input sanity (cheap, before any I/O) ───────────────────────────
        if payload.source_station_code == payload.destination_station_code:
            raise RailMindException(
                code="RM-FARE-002",
                message="Source and destination stations cannot be the same",
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            )
        if payload.journey_date < date.today():
            raise RailMindException(
                code="RM-FARE-003",
                message="Journey date cannot be in the past",
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            )

        # ── 2. Cache lookup ───────────────────────────────────────────────────
        cache_key = self._cache_key(payload)
        cached = await redis.get(cache_key)
        if cached:
            return json.loads(cached), True

        # ── 3. Validate train + both stations on its route (in order) ─────────
        #     Reuses TrainService._validate_journey → RM-TRN-001/002/003.
        journey = ValidateJourneyDTO(
            train_number=payload.train_number,
            from_station=payload.source_station_code,
            to_station=payload.destination_station_code,
        )
        train_data, from_stop, to_stop = await TrainService._validate_journey(
            payload.train_number, journey, db
        )

        # train_stations.distance_km is cumulative from origin
        distance_km = to_stop.distance_km - from_stop.distance_km

        # ── 4. Fetch fare rules (one class if filtered, else all) ─────────────
        stmt = select(FareRules)
        if payload.train_class is not None:
            stmt = stmt.where(FareRules.train_class == payload.train_class.value)
        fare_rules = (await db.execute(stmt)).scalars().all()

        if not fare_rules:
            raise RailMindException(
                code="RM-FARE-001",
                message="No fare rules configured for the requested class",
                status_code=status.HTTP_404_NOT_FOUND,
            )

        # ── 5. Compute breakdown per class via the shared calculator ──────────
        fares = [
            self._to_breakdown_dto(
                FareCalculator(
                    fare_rule=rule, train_type=train_data.train_type
                ).calculate(
                    distance_km=distance_km,
                    quota=payload.quota.value,
                    passenger_age=payload.passenger_age,
                    passenger_gender=payload.passenger_gender,
                    include_irctc_charge=True,
                )
            )
            for rule in fare_rules
        ]
        fares.sort(key=lambda f: self._class_sort_key(f.train_class.value))

        # ── 6. Assemble + cache response ──────────────────────────────────────
        response = FareEnquiryResponseDTO(
            train_number=train_data.train_number,
            train_name=train_data.train_name,
            source={
                "code": from_stop.station.station_code,
                "name": from_stop.station.station_name,
            },
            destination={
                "code": to_stop.station.station_code,
                "name": to_stop.station.station_name,
            },
            journey_date=payload.journey_date,
            distance_km=distance_km,
            quota=payload.quota,
            fares=fares,
        )

        data = response.model_dump(mode="json")
        await redis.setex(cache_key, CACHE_TTL_FARE, json.dumps(data))
        return data, False

    # ── helpers ───────────────────────────────────────────────────────────────

    @staticmethod
    def _cache_key(p: FareEnquiryRequestDTO) -> str:
        return (
            "fare:enquiry:"
            f"{p.train_number}:{p.source_station_code}:{p.destination_station_code}:"
            f"{p.journey_date.isoformat()}:{p.quota.value}:"
            f"{p.train_class.value if p.train_class else 'all'}:"
            f"{p.passenger_age if p.passenger_age is not None else 'na'}:"
            f"{(p.passenger_gender or 'na').upper()}"
        )

    @staticmethod
    def _class_sort_key(train_class: str) -> int:
        try:
            return _CLASS_ORDER.index(train_class)
        except ValueError:
            return len(_CLASS_ORDER)

    @staticmethod
    def _to_breakdown_dto(b: FareBreakdown) -> FareBreakdownDTO:
        return FareBreakdownDTO(
            train_class=b.train_class,
            base_fare=b.gross_base_fare,
            telescopic_discount=b.telescopic_discount,
            superfast_charge=b.superfast_charge,
            reservation_charge=b.reservation_charge,
            tatkal_premium=b.tatkal_charge,
            concession_amount=b.concession_amount,
            subtotal=b.subtotal,
            gst=b.gst_amount,
            service_charge=b.irctc_service_charge,
            total_fare=b.total_fare,
        )


fare_enquiry_service = FareEnquiryService()
