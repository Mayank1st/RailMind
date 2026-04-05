import pytz
import logger
from fastapi import status
from sqlalchemy.orm import aliased
from sqlalchemy import and_, select, or_, null
from app.db.models.train import Trains, TrainStations, Stations
from datetime import datetime
from app.schemas.train import SearchTrainDTO
from sqlalchemy.ext.asyncio import AsyncSession
from app.integrations.rapidapi import rapidapi_client
from app.core.exceptions import RailMindException

from app.utils.helpers import get_time_after_hours


class TrainService:

    async def search_trains(
        self,
        payload: SearchTrainDTO,
        db: AsyncSession,
    ) -> dict:
        try:
            # ── 1. Search local DB first ──────────────────────────────────────────
            TS1 = aliased(TrainStations)
            S1 = aliased(Stations)
            TS2 = aliased(TrainStations)
            S2 = aliased(Stations)

            # ── 2. Build time window filter ───────────────────────────────────────
            ist = pytz.timezone("Asia/Kolkata")
            now = datetime.now(ist)
            from_time = now.strftime("%H:%M:%S")
            to_time = get_time_after_hours(payload.hours)

            # Handle overnight wrap-around (e.g., 23:00:00 to 03:00:00)
            if from_time <= to_time:
                time_filter = and_(
                    TS1.departure_time >= from_time, TS1.departure_time <= to_time
                )
            else:
                time_filter = or_(
                    TS1.departure_time >= from_time, TS1.departure_time <= to_time
                )

            # ── 3. Dynamic Query Construction ─────────────────────────────────────
            select_fields = [
                Trains.train_number,
                Trains.train_name,
                Trains.train_type,
                Trains.runs_on_days,
                S1.station_code.label("from_code"),
                S1.station_name.label("from_name"),
                TS1.departure_time.label("departs"),
                TS1.sequence_number.label("from_seq"),
            ]

            # Add conditional destination fields
            if payload.toStationCode:
                select_fields.extend(
                    [
                        S2.station_code.label("to_code"),
                        S2.station_name.label("to_name"),
                        TS2.arrival_time.label("arrives"),
                        TS2.sequence_number.label("to_seq"),
                        (TS2.distance_km - TS1.distance_km).label("journey_km"),
                    ]
                )
            else:
                # Fill with nulls so row.to_code / row.arrives don't throw errors below
                select_fields.extend(
                    [
                        null().label("to_code"),
                        null().label("to_name"),
                        null().label("arrives"),
                        null().label("to_seq"),
                        null().label("journey_km"),
                    ]
                )

            # Start building statement
            stmt = (
                select(*select_fields)
                .select_from(Trains)
                .join(TS1, TS1.train_id == Trains.id)
                .join(S1, S1.id == TS1.station_id)
            )

            # Base conditions
            conditions = [
                S1.station_code == payload.fromStationCode.upper(),
                Trains.is_active == True,
                time_filter,
            ]

            # Conditionally add destination joins and filters
            if payload.toStationCode:
                stmt = stmt.join(TS2, TS2.train_id == Trains.id).join(
                    S2, S2.id == TS2.station_id
                )
                conditions.append(S2.station_code == payload.toStationCode.upper())
                conditions.append(TS1.sequence_number < TS2.sequence_number)

            # Finalize statement
            stmt = stmt.where(and_(*conditions)).order_by(TS1.departure_time)

            result = await db.execute(stmt)
            rows = result.all()

            # ── 4. Filter by today's running day ──────────────────────────────────
            today = now.strftime("%a").lower()  # 'mon', 'tue' etc.

            trains = []
            for row in rows:
                runs_on_days = row.runs_on_days or []

                # Special trains with empty runs_on_days — include with null flag
                if not runs_on_days:
                    runs_today = None
                else:
                    runs_today = today in runs_on_days

                # Skip trains that definitively don't run today
                if runs_today is False:
                    continue

                trains.append(
                    {
                        "train_number": row.train_number,
                        "train_name": row.train_name,
                        "train_type": row.train_type,
                        "from_station": row.from_code,
                        "from_name": row.from_name,
                        "to_station": row.to_code,
                        "to_name": row.to_name,
                        "departs": row.departs,
                        "arrives": row.arrives,
                        "journey_km": row.journey_km,
                        "runs_on_days": runs_on_days,
                        "runs_today": runs_today,
                    }
                )

            # ── 5. Return DB results if found ─────────────────────────────────────
            if trains:
                return {
                    "source": "local_db",
                    "total": len(trains),
                    "from_time": from_time,
                    "to_time": to_time,
                    "trains": trains,
                }

            # ── 6. Fallback to RapidAPI if DB returns nothing ─────────────────────
            rapidapi_data = await rapidapi_client(
                payload.fromStationCode,
                payload.toStationCode,
                payload.hours,
            )

            return {
                "source": "rapidapi",
                "total": len(rapidapi_data.get("data", [])),
                "trains": rapidapi_data,
            }

        except RailMindException:
            raise

        except Exception as e:
            # traceback.print_exc()
            raise RailMindException(
                code="RM-TRAIN-001",
                message="Failed to fetch train data",
                status_code=500,
            )

    async def get_train_details_by_train_number(
        self, train_number: int, db: AsyncSession
    ) -> dict:
        try:
            train_number = str(train_number)
            result = await db.execute(
                select(Trains).where(Trains.train_number == train_number)
            )
            data = result.scalar_one_or_none()

            if data is None:
                raise RailMindException(
                    code="RM-TRAIN-002",
                    message="Failed to fetch train data",
                    status_code=status.HTTP_404_NOT_FOUND,
                )

            return {
                "id": data.id,
                "train_number": data.train_number,
                "train_name": data.train_name,
                "train_type": data.train_type,
                "run_on_days": data.runs_on_days,
            }
        except Exception as e:
            print(f"Error: {e}")
            raise

    async def get_train_schedule(self, train_number: int, db: AsyncSession) -> dict:
        try:
            result = await db.execute(
                select(Trains).where(Trains.train_number == train_number)
            )
            data = result.scalar_one_or_none()

            if data is None:
                raise RailMindException(
                    code="RM-TRAIN-003",
                    message="Failed to fetch train data",
                    status_code=status.HTTP_404_NOT_FOUND,
                )

            result = await db.execute(
                select(
                    TrainStations.sequence_number,
                    TrainStations.arrival_time,
                    TrainStations.departure_time,
                    TrainStations.distance_km,
                    TrainStations.halt_minutes,
                    TrainStations.is_source,
                    TrainStations.is_destination,
                    Stations.station_code,
                    Stations.station_name,
                )
                .join(Stations, Stations.id == TrainStations.station_id)
                .where(TrainStations.train_id == data.id)
                .order_by(TrainStations.sequence_number)
            )

            stops = result.fetchall()
            return {
                "train_number": data.train_number,
                "train_name": data.train_name,
                "train_type": data.train_type,
                "runs_on_days": data.runs_on_days,
                "total_stops": len(stops),
                "schedule": [
                    {
                        "seq": row.sequence_number,
                        "station_code": row.station_code,
                        "station_name": row.station_name,
                        "arrival": row.arrival_time or "Origin",
                        "departure": row.departure_time or "Terminus",
                        "distance_km": row.distance_km,
                        "halt_minutes": row.halt_minutes,
                        "is_source": row.is_source,
                        "is_destination": row.is_destination,
                    }
                    for row in stops
                ],
            }

        except Exception as e:
            print(f"Error : {e}")
            raise
