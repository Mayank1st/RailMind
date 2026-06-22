import asyncio
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.booking import BookingPassengers
from app.db.models.train import SeatInventories
from tests.conftest import test_engine

BOOKINGS_URL = "/api/v1/bookings/"


async def test_concurrent_bookings_for_last_seat_dont_oversell(
    racing_client, concurrency_world
):
    """
    The real prize: fire TWO booking requests at the SAME last seat concurrently.
    Postgres' SELECT FOR UPDATE serializes them — exactly one wins the confirmed
    seat (CNF), the other is cleanly waitlisted (WL). No oversell, no crash.

    This is precisely the case SQLite could not test: its row lock is a no-op, so
    both requests would "win" and the test would lie.
    """
    payload = {
        "train_number": concurrency_world["train_number"],
        "journey_date": concurrency_world["journey_date"],
        "from_station": concurrency_world["from_station"],
        "to_station": concurrency_world["to_station"],
        "train_class": concurrency_world["train_class"],
        "quota": concurrency_world["quota"],
        "passengers": [{"passenger_id": concurrency_world["passenger_id"]}],
    }

    first, second = await asyncio.gather(
        racing_client.post(BOOKINGS_URL, json=payload),
        racing_client.post(BOOKINGS_URL, json=payload),
    )

    assert first.status_code == 200, first.text
    assert second.status_code == 200, second.text

    outcomes = sorted(
        [first.json()["data"]["availability"], second.json()["data"]["availability"]]
    )
    assert outcomes == ["AVAILABLE", "WL"]

    # The DB itself agrees: the single seat went exactly once, no negative count.
    async with AsyncSession(test_engine, expire_on_commit=False) as session:
        inventory = await session.get(
            SeatInventories, UUID(concurrency_world["inventory_id"])
        )
        assert inventory.available_confirmed_seats == 0

        confirmed = await session.scalar(
            select(func.count())
            .select_from(BookingPassengers)
            .where(BookingPassengers.passenger_status == "CNF")
        )
        assert confirmed == 1
