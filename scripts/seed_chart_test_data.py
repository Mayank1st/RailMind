"""
scripts/seed_chart_test_data.py

Seeds a PERSISTENT, isolated chart-prep test scenario (fixed UUIDs) so you can
inspect it in psql/DBeaver, run chart prep, and watch the changes. Idempotent —
re-running wipes the prior test rows first. Does NOT clean up afterwards (use the
DELETE block / --clean flag for that).

    python scripts/seed_chart_test_data.py            # seed
    python scripts/seed_chart_test_data.py --clean    # remove the test rows
"""

import asyncio
import sys
import uuid
from datetime import date, datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import delete, func, select

from app.db.models.booking import Bookings, BookingPassengers, RACSlots
from app.db.models.passengers import Passengers
from app.db.models.train import Coaches, SeatInventories, Seats, Stations, Trains
from app.db.models.user import Users
from app.db.models.waiting_list import WaitlistEntries
from app.db.session import async_session_local

JD = date(2026, 7, 1)
NOW = datetime.now(timezone.utc)

TRAIN = uuid.UUID("a0000000-0000-0000-0000-000000000001")
COACH = uuid.UUID("a0000000-0000-0000-0000-000000000002")
SEAT = uuid.UUID("a0000000-0000-0000-0000-000000000003")
INV = uuid.UUID("a0000000-0000-0000-0000-000000000004")
PAX = {
    n: uuid.UUID(f"b0000000-0000-0000-0000-00000000000{i}")
    for i, n in enumerate(["RAC1", "RAC2", "GNWL", "PQWL", "TQWL"], start=1)
}
BK = {
    n: uuid.UUID(f"c0000000-0000-0000-0000-00000000000{i}")
    for i, n in enumerate(["rac", "gnwl", "pqwl", "tqwl"], start=1)
}
BP = {
    n: uuid.UUID(f"d0000000-0000-0000-0000-00000000000{i}")
    for i, n in enumerate(["rac1", "rac2", "gnwl", "pqwl", "tqwl"], start=1)
}


async def clean(db):
    await db.execute(
        delete(WaitlistEntries).where(WaitlistEntries.seat_inventory_id == INV)
    )
    await db.execute(delete(RACSlots).where(RACSlots.seat_inventory_id == INV))
    await db.execute(
        delete(BookingPassengers).where(BookingPassengers.seat_inventory_id == INV)
    )
    await db.execute(delete(Bookings).where(Bookings.train_id == TRAIN))
    await db.execute(delete(SeatInventories).where(SeatInventories.train_id == TRAIN))
    await db.execute(delete(Seats).where(Seats.coach_id == COACH))
    await db.execute(delete(Coaches).where(Coaches.train_id == TRAIN))
    await db.execute(delete(Passengers).where(Passengers.id.in_(list(PAX.values()))))
    await db.execute(delete(Trains).where(Trains.id == TRAIN))


async def main(do_clean: bool):
    async with async_session_local() as db:
        await clean(db)  # idempotent wipe of prior test rows
        if do_clean:
            await db.commit()
            print("🧹 chart test rows removed.")
            return

        U = (await db.execute(select(Users.id).limit(1))).scalar()
        S1, S2 = (
            (await db.execute(select(Stations.id).order_by(Stations.id).limit(2)))
            .scalars()
            .all()
        )

        db.add_all(
            [
                Trains(
                    id=TRAIN,
                    train_number="TCHARTSQL",
                    train_name="CHART SQL DEMO",
                    train_type="express",
                    source_station_id=S1,
                    destination_station_id=S2,
                    runs_on_days=["mon", "tue", "wed", "thu", "fri", "sat", "sun"],
                ),
                Coaches(
                    id=COACH,
                    train_id=TRAIN,
                    coach_number="S1",
                    train_class="SL",
                    total_seats=2,
                ),
            ]
        )
        await db.flush()
        db.add(Seats(id=SEAT, coach_id=COACH, seat_number=1, berth_type="SL"))
        db.add(
            SeatInventories(
                id=INV,
                train_id=TRAIN,
                journey_date=JD,
                train_class="SL",
                quota="GN",
                total_confirmed_seats=1,
                available_confirmed_seats=1,
                total_rac_berths=1,
                total_rac_slots=2,
                available_rac_slots=0,
                wl_count=3,
                wl_max=200,
                quota_released_seats=0,
                is_chart_prepared=False,
                chart_status="NOT_PREPARED",
            )
        )
        for name, pid in PAX.items():
            db.add(Passengers(id=pid, user_id=U, full_name=name, age=30, gender="M"))
        for name, bid in BK.items():
            db.add(
                Bookings(
                    id=bid,
                    user_id=U,
                    train_id=TRAIN,
                    pnr_number={
                        "rac": "9100000001",
                        "gnwl": "9100000002",
                        "pqwl": "9100000003",
                        "tqwl": "9100000004",
                    }[name],
                    booking_status="rac" if name == "rac" else "waitlisted",
                    journey_date=JD,
                    source_station_id=S1,
                    destination_station_id=S2,
                    train_class="SL",
                    quota="GN",
                    total_fare=500.0,
                    booked_at=NOW,
                )
            )
        await db.flush()
        # 2 RAC passengers
        db.add_all(
            [
                BookingPassengers(
                    id=BP["rac1"],
                    booking_id=BK["rac"],
                    seat_inventory_id=INV,
                    passenger_id=PAX["RAC1"],
                    berth_preference="NP",
                    passenger_status="RAC",
                    fare=500.0,
                ),
                BookingPassengers(
                    id=BP["rac2"],
                    booking_id=BK["rac"],
                    seat_inventory_id=INV,
                    passenger_id=PAX["RAC2"],
                    berth_preference="NP",
                    passenger_status="RAC",
                    fare=500.0,
                ),
            ]
        )
        # 3 WL passengers
        for nm, bp_id, bk_key, pax_key in [
            ("GNWL", BP["gnwl"], "gnwl", "GNWL"),
            ("PQWL", BP["pqwl"], "pqwl", "PQWL"),
            ("TQWL", BP["tqwl"], "tqwl", "TQWL"),
        ]:
            db.add(
                BookingPassengers(
                    id=bp_id,
                    booking_id=BK[bk_key],
                    seat_inventory_id=INV,
                    passenger_id=PAX[pax_key],
                    berth_preference="NP",
                    passenger_status="WL",
                    fare=500.0,
                )
            )
        await db.flush()
        db.add(
            RACSlots(
                id=uuid.UUID("e0000000-0000-0000-0000-000000000001"),
                seat_inventory_id=INV,
                coach_id=COACH,
                seat_id=SEAT,
                slot_number=1,
                passenger_1_booking_passenger_id=BP["rac1"],
                passenger_2_booking_passenger_id=BP["rac2"],
                is_full=True,
            )
        )
        for i, (wt, bp_key, bk_key) in enumerate(
            [
                ("GNWL", "gnwl", "gnwl"),
                ("PQWL", "pqwl", "pqwl"),
                ("TQWL", "tqwl", "tqwl"),
            ],
            start=1,
        ):
            db.add(
                WaitlistEntries(
                    id=uuid.UUID(f"f0000000-0000-0000-0000-00000000000{i}"),
                    booking_id=BK[bk_key],
                    booking_passenger_id=BP[bp_key],
                    seat_inventory_id=INV,
                    train_class="SL",
                    quota="GN",
                    wl_type=wt,
                    booking_position=i,
                    current_position=i,
                    source_station_id=S1,
                    destination_station_id=S2,
                    is_promoted=False,
                    is_auto_cancelled=False,
                )
            )
        await db.commit()

        # show seeded state
        rows = (
            await db.execute(
                select(Passengers.full_name, BookingPassengers.passenger_status)
                .join(
                    BookingPassengers, BookingPassengers.passenger_id == Passengers.id
                )
                .where(BookingPassengers.seat_inventory_id == INV)
            )
        ).all()
        inv = (
            await db.execute(select(SeatInventories).where(SeatInventories.id == INV))
        ).scalar_one()
        print(
            "✅ Seeded (persistent). Train=TCHARTSQL  inventory id =",
            INV,
            " journey_date =",
            JD,
        )
        for name, st in sorted(rows):
            print(f"   {name:<6} → {st}")
        print(
            f"   inventory: chart_status={inv.chart_status} avail_CNF={inv.available_confirmed_seats} "
            f"avail_RAC={inv.available_rac_slots} wl_count={inv.wl_count}"
        )


if __name__ == "__main__":
    asyncio.run(main("--clean" in sys.argv))
