import pytz
import logger
from fastapi import status
from typing import Optional
from sqlalchemy.orm import aliased, selectinload
from sqlalchemy import and_, select, or_, null, exists
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
from app.schemas.train import (
    SearchTrainDTO,
    CheckSeatAvailabilityDTO,
    ValidateJourneyDTO,
)
from app.schemas.Response.trainResponseDTO import (
    TrainDetailResponse,
    CoachWiseSeatAvailabilityResponse,
)
from sqlalchemy.ext.asyncio import AsyncSession
from fastapi_pagination import Params
from fastapi_pagination.ext.sqlalchemy import apaginate
from app.core.exceptions import RailMindException
from app.services.station_cluster_service import station_cluster_service
from app.core.constants.booking import PassengerStatus
from app.schemas.Request.trainFilterDTO import TrainFilter

from app.utils.helpers import get_time_after_hours


class TrainService:

    async def list_trains(
        self,
        db: AsyncSession,
        train_filter: TrainFilter,
        params: Params,
    ):
        """
        Generic list endpoint — reference implementation of the
        filter + sort + paginate pattern. Reuse this shape for any resource.
        """
        query = select(Trains).options(
            selectinload(Trains.source_station),
            selectinload(Trains.destination_station),
        )
        query = train_filter.filter(query)  # WHERE: field filters + search
        query = train_filter.sort(query)  # ORDER BY: ?order_by=...

        return await apaginate(
            db,
            query,
            params,
            transformer=lambda rows: [self._serialize_train_summary(t) for t in rows],
        )

    @staticmethod
    def _serialize_train_summary(train) -> dict:
        return {
            "train_id": train.id,
            "train_number": train.train_number,
            "train_name": train.train_name,
            "train_type": train.train_type,
            "runs_on_days": train.runs_on_days,
            "source_station": train.source_station.station_code,
            "destination_station": train.destination_station.station_code,
        }

    async def search_trains_list(
        self,
        payload: SearchTrainDTO,
        db: AsyncSession,
    ) -> dict:
        """Core search — returns the full processed train list (no pagination).
        Used by the NLP search path; the paginated `search_trains` wraps this."""
        try:
            # ── 1. Aliases ───────────────────────────────────────────────────
            TS1 = aliased(TrainStations)
            S1 = aliased(Stations)
            TS2 = aliased(TrainStations)
            S2 = aliased(Stations)

            # ── 2. Time window filter ────────────────────────────────────────
            ist = pytz.timezone("Asia/Kolkata")
            now = datetime.now(ist)

            if payload.hours >= 24:
                # 24+ hours = poora din, no time filter
                time_filter = True
                from_time = "all_day"
                to_time = "all_day"
            else:
                from_time = now.strftime("%H:%M:%S")
                to_time = get_time_after_hours(payload.hours)

                if from_time <= to_time:
                    time_filter = and_(
                        TS1.departure_time >= from_time,
                        TS1.departure_time <= to_time,
                    )
                else:
                    time_filter = or_(
                        TS1.departure_time >= from_time,
                        TS1.departure_time <= to_time,
                    )

            # ── 3. Select fields ─────────────────────────────────────────────
            select_fields = [
                Trains.train_number,
                Trains.train_name,
                Trains.train_type,
                Trains.runs_on_days,
                S1.station_code.label("from_code"),
                S1.station_name.label("from_name"),
                TS1.departure_time.label("departs"),
                TS1.day_number.label("dep_day"),
                TS1.sequence_number.label("from_seq"),
            ]

            if payload.toStationCode:
                select_fields.extend(
                    [
                        S2.station_code.label("to_code"),
                        S2.station_name.label("to_name"),
                        TS2.arrival_time.label("arrives"),
                        TS2.day_number.label("arr_day"),
                        TS2.sequence_number.label("to_seq"),
                        (TS2.distance_km - TS1.distance_km).label("journey_km"),
                    ]
                )
            else:
                select_fields.extend(
                    [
                        null().label("to_code"),
                        null().label("to_name"),
                        null().label("arrives"),
                        null().label("arr_day"),
                        null().label("to_seq"),
                        null().label("journey_km"),
                    ]
                )

            # ── 4. Build query ───────────────────────────────────────────────
            stmt = (
                select(*select_fields)
                .select_from(Trains)
                .join(TS1, TS1.train_id == Trains.id)
                .join(S1, S1.id == TS1.station_id)
            )

            # Nearby-stations expansion — when on, match any station in the
            # source/destination clusters; otherwise just the exact code.
            from_req = payload.fromStationCode.upper()
            to_req = payload.toStationCode.upper() if payload.toStationCode else None
            if payload.nearby_stations:
                await station_cluster_service.ensure_loaded(db)
                from_codes = station_cluster_service.expand_station_set(from_req)
                to_codes = (
                    station_cluster_service.expand_station_set(to_req)
                    if to_req
                    else None
                )
            else:
                from_codes = {from_req}
                to_codes = {to_req} if to_req else None

            # Base conditions
            conditions = [
                S1.station_code.in_(from_codes),
                Trains.is_active == True,
            ]

            # Time filter — sirf hours < 24 pe apply
            if time_filter is not True:
                conditions.append(time_filter)

            # Train class filter — Coaches EXISTS
            if payload.train_class:
                coach_exists = (
                    exists()
                    .where(Coaches.train_id == Trains.id)
                    .where(Coaches.train_class == payload.train_class)
                )
                conditions.append(coach_exists)

            # Train type filter (express / superfast / rajdhani / ...)
            if payload.train_type:
                conditions.append(Trains.train_type == payload.train_type.lower())

            # Destination joins
            if payload.toStationCode:
                stmt = stmt.join(TS2, TS2.train_id == Trains.id).join(
                    S2, S2.id == TS2.station_id
                )
                conditions.append(S2.station_code.in_(to_codes))
                conditions.append(TS1.sequence_number < TS2.sequence_number)

            # Finalize
            stmt = stmt.where(and_(*conditions)).order_by(TS1.departure_time)
            result = await db.execute(stmt)
            rows = result.all()

            # ── 5. Filter by running day ─────────────────────────────────────
            today = now.strftime("%a").lower()

            trains = []
            for row in rows:
                runs_on_days = row.runs_on_days or []

                if not runs_on_days:
                    runs_today = None
                else:
                    runs_today = today in runs_on_days

                if runs_today is False:
                    continue

                # Exact = the train actually departs from / arrives at the
                # requested codes (vs a nearby cluster member).
                exact_to = (to_req is None) or (row.to_code == to_req)
                is_exact_match = (row.from_code == from_req) and exact_to

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
                        "duration_minutes": self._duration_minutes(
                            row.departs, row.arrives, row.dep_day, row.arr_day
                        ),
                        "runs_on_days": runs_on_days,
                        "runs_today": runs_today,
                        "is_exact_match": is_exact_match,
                    }
                )

            # ── 6. Post-filters + sort (computed fields, so done in Python) ───
            if payload.exact_only:
                trains = [t for t in trains if t["is_exact_match"]]

            if payload.sort_by == "duration":
                # unknown duration sinks to the bottom
                trains.sort(
                    key=lambda t: (
                        t["duration_minutes"]
                        if t["duration_minutes"] is not None
                        else 10**9
                    )
                )
            # default "departure" — SQL already ordered by departure_time

            # ── 7. Return full list (pagination handled by `search_trains`) ───
            return {
                "source": "local_db",
                "total": len(trains),
                "from_time": from_time,
                "to_time": to_time,
                "trains": trains,
            }

        except RailMindException:
            raise

        except Exception as e:
            raise RailMindException(
                code="RM-TRAIN-001",
                message="Failed to fetch train data",
                status_code=500,
            )

    async def search_trains(
        self,
        payload: SearchTrainDTO,
        db: AsyncSession,
    ) -> dict:
        """Paginated search for the HTTP endpoint — page/size come from the
        payload. Slices the bounded `search_trains_list` result in-memory."""
        full = await self.search_trains_list(payload, db)
        trains = full["trains"]
        total = len(trains)
        size = payload.size
        page_no = payload.page
        start = (page_no - 1) * size
        items = trains[start : start + size]
        pages = (total + size - 1) // size if size else 0

        return {
            "items": items,
            "meta": {
                "total": total,
                "page": page_no,
                "size": size,
                "pages": pages,
                "from_time": full["from_time"],
                "to_time": full["to_time"],
                "nearby_stations": payload.nearby_stations,
            },
        }

    @staticmethod
    def _duration_minutes(departs, arrives, dep_day, arr_day) -> int | None:
        """Journey duration in minutes from HH:MM[:SS] times + day numbers.
        None when data is missing/unparseable (e.g. destination-less search)."""
        if not departs or not arrives or dep_day is None or arr_day is None:
            return None
        try:
            dep_min = int(departs[:2]) * 60 + int(departs[3:5])
            arr_min = int(arrives[:2]) * 60 + int(arrives[3:5])
        except (ValueError, IndexError):
            return None
        diff = ((int(arr_day) - 1) * 1440 + arr_min) - (
            (int(dep_day) - 1) * 1440 + dep_min
        )
        if diff < 0:
            diff += 1440  # guard against bad day_number data
        return diff

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
            train_data, from_stop, to_stop = await self._validate_journey(
                train_number, payload=payload, db=db
            )

            # ── Build query — saari classes fetch karo ──
            conditions = [
                SeatInventories.train_id == train_data.id,
                SeatInventories.journey_date == payload.journey_date,
            ]

            # Agar quota aaya toh filter, nahi toh sab dikhao
            if payload.quota:
                conditions.append(SeatInventories.quota == payload.quota)

            inv_result = await db.execute(
                select(SeatInventories).where(and_(*conditions))
            )
            inventories = inv_result.scalars().all()

            if not inventories:
                raise RailMindException(
                    code="RM-TRN-004",
                    message="No availability data found for this train on the selected date",
                    status_code=status.HTTP_404_NOT_FOUND,
                )

            # ── Har class ka data build karo ──
            classes = []
            for inv in inventories:
                wl_type = self._determine_wl_type(
                    is_source=from_stop.is_source,
                    is_remote_location=from_stop.station.is_remote_location,
                    quota=inv.quota,
                )

                # Status decide karo
                if inv.available_confirmed_seats > 0:
                    status_label = "AVL"
                    count = inv.available_confirmed_seats
                elif inv.available_rac_slots > 0:
                    status_label = "RAC"
                    count = inv.available_rac_slots
                else:
                    status_label = "WL"
                    count = inv.next_wl_position

                classes.append(
                    {
                        "class_code": inv.train_class,
                        "quota": inv.quota,
                        "status": status_label,
                        "count": count,
                        "available_seats": inv.available_confirmed_seats,
                        "available_rac_slots": inv.available_rac_slots,
                        "wl_count": inv.wl_count,
                        "next_wl_position": inv.next_wl_position,
                        "wl_type": wl_type,
                    }
                )

            return {
                "train_number": train_data.train_number,
                "train_name": train_data.train_name,
                "journey_date": str(payload.journey_date),
                "from_station": payload.from_station,
                "to_station": payload.to_station,
                "classes": classes,
            }

        except Exception as e:
            raise e

    async def get_seat_availability_by_coach_number(
        self, train_number: str, payload: CheckSeatAvailabilityDTO, db: AsyncSession
    ) -> dict:

        train_data, from_stop, to_stop = await self._validate_journey(
            train_number, payload=payload, db=db
        )

        wl_type = self._determine_wl_type(
            is_source=from_stop.is_source,
            is_remote_location=from_stop.station.is_remote_location,
            quota=payload.quota,
        )

        # ── Coaches filter ────────────────────────────────────────────────────────
        # Note: coaches selectinload _validate_journey mein nahi hai
        # Isliye yahan separately load karna padega
        coaches_result = await db.execute(
            select(Coaches).where(
                Coaches.train_id == train_data.id,
                Coaches.train_class == payload.train_class,
                Coaches.coach_number == payload.coach_number,
            )
        )
        filtered_coaches = coaches_result.scalars().all()

        if not filtered_coaches:
            raise RailMindException(
                code="RM-TRN-005",
                message=f"No {payload.train_class} coaches found on this train",
                status_code=status.HTTP_404_NOT_FOUND,
            )

        # ── Booked seats fetch ────────────────────────────────────────────────────
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

        # ── Seats fetch ───────────────────────────────────────────────────────────
        coach_ids = [c.id for c in filtered_coaches]
        seats_result = await db.execute(
            select(Seats).where(
                Seats.coach_id.in_(coach_ids),
                Seats.is_rac_berth == False,
            )
        )
        all_seats = seats_result.scalars().all()

        # ── seats_by_coach mapping ────────────────────────────────────────────────
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

        # ── coaches_data — loop ke BAAD banana chahiye ────────────────────────────
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
            for coach in sorted(filtered_coaches, key=lambda c: c.coach_position or 0)
        ]

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

    @staticmethod
    def _determine_wl_type(
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

    @staticmethod
    async def _validate_journey(
        train_number: Optional[str],
        payload: ValidateJourneyDTO,
        db: AsyncSession,
    ):

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
        if from_stop.sequence_number >= to_stop.sequence_number:
            raise RailMindException(
                code="RM-TRN-003",
                message=f"{payload.from_station} comes after {payload.to_station} on this route",
                status_code=status.HTTP_400_BAD_REQUEST,
            )

        return train_data, from_stop, to_stop
