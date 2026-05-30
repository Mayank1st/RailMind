from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from fastapi import status

from app.core.fare_calculator import FareCalculator, FareBreakdown
from app.db.models.booking import FareRules
from app.db.models.train import TrainStations, Stations
from app.core.exceptions import RailMindException


class CommonService:

    async def calculate_fare(
        self,
        db: AsyncSession,
        train_type: str,
        train_class: str,
        from_stop: TrainStations,
        to_stop: TrainStations,
        quota: str,
        passenger_age: int | None = None,
        passenger_gender: str | None = None,
        include_irctc_charge: bool = False,
        pt_multiplier: float | None = None,
    ) -> FareBreakdown:

        # ── FareRule fetch karo ───────────────────────────────────────────────
        result = await db.execute(
            select(FareRules).where(FareRules.train_class == train_class)
        )
        fare_rule = result.scalar_one_or_none()

        if not fare_rule:
            raise RailMindException(
                code="RM-FARE-001",
                message=f"Fare rule not found for class {train_class}",
                status_code=status.HTTP_404_NOT_FOUND,
            )

        # ── Distance calculate karo ───────────────────────────────────────────
        # train_stations.distance_km cumulative hai origin se
        # to_stop - from_stop = actual journey distance
        distance_km = to_stop.distance_km - from_stop.distance_km

        if distance_km <= 0:
            raise RailMindException(
                code="RM-FARE-002",
                message="Invalid distance — from station comes after to station",
                status_code=status.HTTP_400_BAD_REQUEST,
            )

        # ── Calculate karo ────────────────────────────────────────────────────
        calculator = FareCalculator(fare_rule=fare_rule, train_type=train_type)

        return calculator.calculate(
            distance_km=distance_km,
            quota=quota,
            passenger_age=passenger_age,
            passenger_gender=passenger_gender,
            include_irctc_charge=include_irctc_charge,
            pt_multiplier=pt_multiplier,
        )

    async def get_all_stations(self, db: AsyncSession) -> list[dict]:
        result = await db.execute(select(Stations).order_by(Stations.station_code))
        stations = result.scalars().all()
        return [
            {"station_code": station.station_code, "station_name": station.station_name}
            for station in stations
        ]


common_service = CommonService()
