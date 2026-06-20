"""
scripts/test_chart_preparation.py

Self-contained chart-preparation demo/test. Seeds ONE isolated fake train with a
clear CNF/RAC/WL/TQWL scenario, runs Stage 1 + Stage 2, prints the before→after
state, then deletes everything it created (no real data touched).

Usage:
    python scripts/test_chart_preparation.py
"""

import asyncio
import random
import sys
import uuid
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import delete, func, select

from app.db.models.booking import Bookings, BookingPassengers, RACSlots
from app.db.models.passengers import Passengers
from app.db.models.train import Coaches, SeatInventories, Seats, Stations, Trains
from app.db.models.user import Users
from app.db.models.waiting_list import WaitlistEntries
from app.db.session import async_session_local
from app.services.chart_preparation_service import chart_preparation_service as CP

JD = date.today() + timedelta(days=1)
NOW = datetime.now(timezone.utc)
ids: dict = {}


def nid(key: str) -> uuid.UUID:
    ids[key] = uuid.uuid4()
    return ids[key]


async def _refs(db):
    """Borrow a real user + two stations (FKs require them)."""
    u = (await db.execute(select(Users.id).limit(1))).scalar()
    s = (await db.execute(select(Stations.id).limit(2))).scalars().all()
    return u, s[0], s[1]


async def seed():
    async with async_session_local() as db:
        U, S1, S2 = await _refs(db)
        ids["U"], ids["S1"], ids["S2"] = U, S1, S2

        db.add_all(
            [
                Trains(
                    id=nid("train"),
                    train_number="TCHART001",
                    train_name="CHART DEMO",
                    source_station_id=S1,
                    destination_station_id=S2,
                    runs_on_days=["mon", "tue", "wed", "thu", "fri", "sat", "sun"],
                ),
                Coaches(
                    id=nid("coach"),
                    train_id=ids["train"],
                    coach_number="S1",
                    train_class="SL",
                    total_seats=2,
                ),
            ]
        )
        await db.flush()
        db.add(
            Seats(id=nid("seat"), coach_id=ids["coach"], seat_number=1, berth_type="SL")
        )
        await db.flush()

        # 1 free CNF seat, 0 free RAC slots (2 RAC pax fill 1 berth), 3 WL.
        db.add(
            SeatInventories(
                id=nid("inv"),
                train_id=ids["train"],
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
            )
        )
        await db.flush()

        def pax(n):
            return Passengers(
                id=uuid.uuid4(), user_id=U, full_name=n, age=30, gender="M"
            )

        def bk(tag, st):
            return Bookings(
                id=nid("bk_" + tag),
                user_id=U,
                train_id=ids["train"],
                pnr_number="".join(random.choices("0123456789", k=10)),
                booking_status=st,
                journey_date=JD,
                source_station_id=S1,
                destination_station_id=S2,
                train_class="SL",
                quota="GN",
                total_fare=500.0,
                booked_at=NOW,
            )

        def bp(tag, bid, pid, s):
            return BookingPassengers(
                id=nid("bp_" + tag),
                booking_id=bid,
                seat_inventory_id=ids["inv"],
                passenger_id=pid,
                berth_preference="NP",
                passenger_status=s,
                fare=500.0,
            )

        # 2 RAC passengers (1 RAC berth, both slots full)
        p1, p2 = pax("RAC1"), pax("RAC2")
        db.add_all([p1, p2])
        await db.flush()
        bkr = bk("rac", "rac")
        db.add(bkr)
        await db.flush()
        b1, b2 = bp("rac1", bkr.id, p1.id, "RAC"), bp("rac2", bkr.id, p2.id, "RAC")
        db.add_all([b1, b2])
        await db.flush()
        db.add(
            RACSlots(
                id=nid("slot"),
                seat_inventory_id=ids["inv"],
                coach_id=ids["coach"],
                seat_id=ids["seat"],
                slot_number=1,
                passenger_1_booking_passenger_id=b1.id,
                passenger_2_booking_passenger_id=b2.id,
                is_full=True,
            )
        )

        # 3 waitlisted: GNWL, PQWL, TQWL
        for tag, wt, pos in [
            ("gnwl", "GNWL", 1),
            ("pqwl", "PQWL", 2),
            ("tqwl", "TQWL", 3),
        ]:
            p = pax(tag.upper())
            db.add(p)
            await db.flush()
            b = bk(tag, "waitlisted")
            db.add(b)
            await db.flush()
            x = bp(tag, b.id, p.id, "WL")
            db.add(x)
            await db.flush()
            db.add(
                WaitlistEntries(
                    id=uuid.uuid4(),
                    booking_id=b.id,
                    booking_passenger_id=x.id,
                    seat_inventory_id=ids["inv"],
                    train_class="SL",
                    quota="GN",
                    wl_type=wt,
                    booking_position=pos,
                    current_position=pos,
                    source_station_id=S1,
                    destination_station_id=S2,
                    is_promoted=False,
                    is_auto_cancelled=False,
                )
            )

        await db.commit()


async def snapshot(label):
    keys = {
        "bp_rac1": "RAC1",
        "bp_rac2": "RAC2",
        "bp_gnwl": "GNWL(wl)",
        "bp_pqwl": "PQWL(wl)",
        "bp_tqwl": "TQWL(wl)",
    }
    async with async_session_local() as db:
        print(f"\n── {label} ──")
        for k, name in keys.items():
            st = (
                await db.execute(
                    select(BookingPassengers.passenger_status).where(
                        BookingPassengers.id == ids[k]
                    )
                )
            ).scalar()
            print(f"   {name:<10} → {st}")
        inv = (
            await db.execute(
                select(SeatInventories).where(SeatInventories.id == ids["inv"])
            )
        ).scalar_one()
        cnf = (
            await db.execute(
                select(func.count())
                .select_from(BookingPassengers)
                .where(
                    BookingPassengers.seat_inventory_id == ids["inv"],
                    BookingPassengers.passenger_status == "CNF",
                )
            )
        ).scalar()
        print(
            f"   inventory: chart_status={inv.chart_status} | "
            f"avail_CNF={inv.available_confirmed_seats} avail_RAC={inv.available_rac_slots} "
            f"wl_count={inv.wl_count} | CNF_booked={cnf}/{inv.total_confirmed_seats}"
        )


async def cleanup():
    if "inv" not in ids:  # seed failed before anything was committed
        return
    async with async_session_local() as db:
        for s in [
            delete(WaitlistEntries).where(
                WaitlistEntries.seat_inventory_id == ids["inv"]
            ),
            delete(RACSlots).where(RACSlots.seat_inventory_id == ids["inv"]),
            delete(BookingPassengers).where(
                BookingPassengers.seat_inventory_id == ids["inv"]
            ),
            delete(Bookings).where(Bookings.train_id == ids["train"]),
            delete(SeatInventories).where(SeatInventories.train_id == ids["train"]),
            delete(Seats).where(Seats.coach_id == ids["coach"]),
            delete(Coaches).where(Coaches.train_id == ids["train"]),
            delete(Passengers).where(
                Passengers.full_name.in_(["RAC1", "RAC2", "GNWL", "PQWL", "TQWL"]),
                Passengers.user_id == ids["U"],
            ),
            delete(Trains).where(Trains.id == ids["train"]),
        ]:
            await db.execute(s)
        await db.commit()


async def main():
    print("=" * 64)
    print("  Chart Preparation — isolated demo")
    print("  Scenario: 1 free CNF seat | 2 RAC pax | 3 WL (GNWL, PQWL, TQWL)")
    print("=" * 64)
    try:
        await seed()
        await snapshot("BEFORE (freshly booked)")

        async with async_session_local() as db:
            ch1 = await CP.prepare_chart(db, ids["train"], JD, stage=1)
        await snapshot(f"AFTER STAGE 1  (changes={len(ch1)})")
        print("   expect: RAC1→CNF, GNWL→RAC, PQWL & TQWL → AUTO_CANCELLED_CHART")

        async with async_session_local() as db:
            ch2 = await CP.prepare_chart(db, ids["train"], JD, stage=2)
        await snapshot(f"AFTER STAGE 2  (changes={len(ch2)})")
        print("   expect: no overbooking — RAC2 stays RAC (no free seat left)")

        # idempotency
        async with async_session_local() as db:
            again = await CP.prepare_chart(db, ids["train"], JD, stage=1)
        print(f"\n── Idempotency: re-run Stage 1 → changes={len(again)} (expect 0) ──")
        print("\n✅ Done. Compare the arrows above with the 'expect' lines.")
    finally:
        await cleanup()
        print("🧹 (test rows cleaned up — no real data touched)")


if __name__ == "__main__":
    asyncio.run(main())
