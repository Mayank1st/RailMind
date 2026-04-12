import pytz
import logger
from fastapi import status
from sqlalchemy.orm import aliased, selectinload
from sqlalchemy import and_, select, or_, null
from app.db.models.train import (
    Trains,
    TrainStations,
    Stations,
    SeatInventories,
    Coaches,
    Seats,
)
from app.db.models.booking import BookingPassengers, Bookings
from datetime import datetime
from app.schemas.train import SearchTrainDTO, CheckSeatAvailabilityDTO
from app.schemas.Response.trainResponseDTO import (
    TrainDetailResponse,
    CoachWiseSeatAvailabilityResponse,
)
from sqlalchemy.ext.asyncio import AsyncSession
from app.integrations.rapidapi import rapidapi_client
from app.core.exceptions import RailMindException
from app.core.constants.booking import PassengerStatus

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
                select(Trains)
                .options(selectinload(Trains.coaches))
                .where(Trains.train_number == train_number)
            )
            data = result.scalar_one_or_none()

            if data is None:
                raise RailMindException(
                    code="RM-TRAIN-002",
                    message="Failed to fetch train data",
                    status_code=status.HTTP_404_NOT_FOUND,
                )

            return TrainDetailResponse.model_validate(data)
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

    async def get_seat_availability(
        self, train_number: str, payload: CheckSeatAvailabilityDTO, db: AsyncSession
    ) -> dict:
        try:
            result = await db.execute(
                select(Trains)
                .options(selectinload(Trains.stops).selectinload(TrainStations.station))
                .where(Trains.train_number == train_number)
            )
            train_data = result.scalar_one_or_none()

            if not train_data:
                raise RailMindException(
                    code="RM-TRN-001",
                    message="Train not found",
                    status_code=status.HTTP_404_NOT_FOUND,
                )

            from_stop = next(
                (
                    s
                    for s in train_data.stops
                    if s.station.station_code == payload.from_station
                ),
                None,
            )
            to_stop = next(
                (
                    s
                    for s in train_data.stops
                    if s.station.station_code == payload.to_station
                ),
                None,
            )

            if not from_stop:
                raise RailMindException(
                    code="RM-TRN-002",
                    message=f"Station {payload.from_station} not found on this train route",
                    status_code=status.HTTP_400_BAD_REQUEST,
                )
            if not to_stop:
                raise RailMindException(
                    code="RM-TRN-002",
                    message=f"Station {payload.to_station} not found on this train route",
                    status_code=status.HTTP_400_BAD_REQUEST,
                )

            # ── Sequence check ───────────────────────────────────────────────────
            if from_stop.sequence_number >= to_stop.sequence_number:
                raise RailMindException(
                    code="RM-TRN-003",
                    message=f"{payload.from_station} comes after {payload.to_station} on this route",
                    status_code=status.HTTP_400_BAD_REQUEST,
                )

            wl_type = self._determine_wl_type(
                is_source=from_stop.is_source,
                is_remote_location=from_stop.station.is_remote_location,
                quota=payload.quota,
            )

            inv_result = await db.execute(
                select(SeatInventories).where(
                    SeatInventories.train_id == train_data.id,
                    SeatInventories.journey_date == payload.journey_date,
                    SeatInventories.train_class == payload.train_class,
                    SeatInventories.quota == payload.quota,
                )
            )
            inventory = inv_result.scalar_one_or_none()

            if not inventory:
                raise RailMindException(
                    code="RM-TRN-004",
                    message="No availability data found for this train on the selected date",
                    status_code=status.HTTP_404_NOT_FOUND,
                )

            # ── Availability status decide karo ──────────────────────────────────
            availability_status = inventory.booking_availability

            return {
                "train_number": train_data.train_number,
                "train_name": train_data.train_name,
                "journey_date": payload.journey_date,
                "from_station": payload.from_station,
                "to_station": payload.to_station,
                "train_class": payload.train_class,
                "quota": payload.quota,
                "availability_status": availability_status,
                "available_seats": inventory.available_confirmed_seats,
                "available_rac_slots": inventory.available_rac_slots,
                "wl_count": inventory.wl_count,
                "next_wl_position": inventory.next_wl_position,
                "wl_type": wl_type,
            }

        except Exception as e:
            raise e

    def _determine_wl_type(
        self,
        is_source: bool,
        is_remote_location: bool,
        quota: str,
    ) -> str:
        if quota in ("TQ", "PT"):
            return "TQWL"
        if is_source:
            return "GNWL"
        if is_remote_location:
            return "RLWL"
        return "PQWL"

    async def get_seat_availability_by_coach_number(
        self, train_number: str, payload: CheckSeatAvailabilityDTO, db: AsyncSession
    ) -> dict:
        result = await db.execute(
            select(Trains)
            .options(
                selectinload(Trains.stops).selectinload(TrainStations.station),
                selectinload(Trains.coaches),
            )
            .where(Trains.train_number == train_number)
        )
        train_data = result.scalar_one_or_none()

        if not train_data:
            raise RailMindException(
                code="RM-TRN-001",
                message="Train not found",
                status_code=status.HTTP_404_NOT_FOUND,
            )

        # ── from/to stop dhundho ─────────────────────────────────────────────────
        from_stop = next(
            (
                s
                for s in train_data.stops
                if s.station.station_code == payload.from_station
            ),
            None,
        )
        to_stop = next(
            (
                s
                for s in train_data.stops
                if s.station.station_code == payload.to_station
            ),
            None,
        )

        if not from_stop:
            raise RailMindException(
                code="RM-TRN-002",
                message=f"Station {payload.from_station} not found on this train route",
                status_code=status.HTTP_400_BAD_REQUEST,
            )
        if not to_stop:
            raise RailMindException(
                code="RM-TRN-002",
                message=f"Station {payload.to_station} not found on this train route",
                status_code=status.HTTP_400_BAD_REQUEST,
            )

        # ── Sequence check ───────────────────────────────────────────────────────
        if from_stop.sequence_number >= to_stop.sequence_number:
            raise RailMindException(
                code="RM-TRN-003",
                message=f"{payload.from_station} comes after {payload.to_station} on this route",
                status_code=status.HTTP_400_BAD_REQUEST,
            )

        # ── WL type decide karo ──────────────────────────────────────────────────
        wl_type = self._determine_wl_type(
            is_source=from_stop.is_source,
            is_remote_location=from_stop.station.is_remote_location,
            quota=payload.quota,
        )

        # ── Requested class ke coaches filter karo ───────────────────────────────
        filtered_coaches = [
            c
            for c in train_data.coaches
            if c.train_class == payload.train_class
            and c.coach_number == payload.coach_number
        ]

        if not filtered_coaches:
            raise RailMindException(
                code="RM-TRN-005",
                message=f"No {payload.train_class} coaches found on this train",
                status_code=status.HTTP_404_NOT_FOUND,
            )

        # ── Already booked seat_ids fetch karo is journey ke liye ────────────────
        # Yeh seats CNF passengers ko assign hain — inhe vacant nahi dikhana
        booked_seats_result = await db.execute(
            select(BookingPassengers.seat_id)
            .join(Bookings, Bookings.id == BookingPassengers.booking_id)
            .where(
                Bookings.train_id == train_data.id,
                Bookings.journey_date == payload.journey_date,
                Bookings.train_class == payload.train_class,
                BookingPassengers.passenger_status == PassengerStatus.CONFIRMED,
                BookingPassengers.seat_id.is_not(None),
            )
        )
        booked_seat_ids = {row.seat_id for row in booked_seats_result.fetchall()}

        # ── Har coach ke liye seats load karo ────────────────────────────────────
        coach_ids = [c.id for c in filtered_coaches]
        seats_result = await db.execute(
            select(Seats).where(
                Seats.coach_id.in_(coach_ids),
                Seats.is_rac_berth == False,  # RAC berths confirmed seats nahi hain
            )
        )
        all_seats = seats_result.scalars().all()

        # Coach id → seats mapping banao
        seats_by_coach: dict = {}
        for seat in all_seats:
            coach_id_str = str(seat.coach_id)
            if coach_id_str not in seats_by_coach:
                seats_by_coach[coach_id_str] = []
            seats_by_coach[coach_id_str].append(
                {
                    "seat_number": seat.seat_number,
                    "berth_type": seat.berth_type,
                    "is_available": seat.id not in booked_seat_ids,
                }
            )

            coaches_data = [
                {
                    "coach_number": coach.coach_number,
                    "train_class": coach.train_class,
                    "total_seats": coach.total_seats,
                    "coach_position": coach.coach_position,
                    "available_seats": sum(
                        1
                        for s in seats_by_coach.get(str(coach.id), [])
                        if s["is_available"]
                    ),
                    "seats": seats_by_coach.get(str(coach.id), []),
                }
                for coach in sorted(
                    filtered_coaches, key=lambda c: c.coach_position or 0
                )
            ]

        # ── Coach-wise response banao ─────────────────────────────────────────────
        return CoachWiseSeatAvailabilityResponse.model_validate(
            {
                "train_number": train_data.train_number,
                "train_name": train_data.train_name,
                "journey_date": payload.journey_date,
                "from_station": payload.from_station,
                "to_station": payload.to_station,
                "train_class": payload.train_class,
                "quota": payload.quota,
                "wl_type": wl_type,
                "coaches": coaches_data,
            }
        )
