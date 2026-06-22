import os
import subprocess
import sys
from datetime import date
from pathlib import Path
from urllib.parse import quote_plus

import httpx
import psycopg
import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    create_async_engine,
)
from sqlalchemy.pool import NullPool

from app.api.deps import get_current_user
from app.config import settings
from app.db.session import get_db
from app.domain.common.common_service.common_service import common_service
from app.db.models.booking import FareRules
from app.db.models.passengers import Passengers
from app.db.models.train import (
    Coaches,
    SeatInventories,
    Seats,
    Stations,
    TrainStations,
    Trains,
)
from app.db.models.user import Users
from app.main import app

TEST_DB_NAME = "railmind_test"
REPO_ROOT = Path(__file__).resolve().parents[1]

TEST_USER_ID = "00000000-0000-0000-0000-000000000001"
TEST_PASSENGER_ID = "11111111-1111-1111-1111-111111111111"

_test_db_url = (
    f"postgresql+asyncpg://{settings.DB_USERNAME}:"
    f"{quote_plus(settings.DB_PASSWORD)}@"
    f"{settings.DB_HOST}:{settings.DB_PORT}/{TEST_DB_NAME}"
)

# A dedicated engine bound to the test DB. The app's own engine (app/db/base.py)
test_engine = create_async_engine(
    _test_db_url,
    poolclass=NullPool,
    connect_args={"server_settings": {"search_path": f'"{settings.DB_SCHEMA}"'}},
)


def _ensure_test_database() -> None:
    """Create the test database if it doesn't exist (connects to `postgres`)."""
    with psycopg.connect(
        host=settings.DB_HOST,
        port=settings.DB_PORT,
        user=settings.DB_USERNAME,
        password=settings.DB_PASSWORD,
        dbname="postgres",
        autocommit=True,
    ) as conn:
        exists = conn.execute(
            "SELECT 1 FROM pg_database WHERE datname = %s", (TEST_DB_NAME,)
        ).fetchone()
        if not exists:
            conn.execute(f'CREATE DATABASE "{TEST_DB_NAME}"')


def _run_migrations() -> None:
    """Bring the test DB to head — the same alembic path production uses."""
    subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        cwd=REPO_ROOT,
        env={**os.environ, "DB_NAME": TEST_DB_NAME},
        check=True,
    )


@pytest.fixture(scope="session")
def _test_db():
    """Provision the test DB once per run. Only integration tests depend on it,
    so pure unit tests stay DB-free and fast."""
    _ensure_test_database()
    _run_migrations()
    yield


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture
async def db_session(_test_db):
    """
    A session wrapped in an outer transaction that is ALWAYS rolled back after
    the test — so every test starts from the same clean DB, and nothing it
    writes survives.

    The trick: open one connection, begin an outer transaction, and bind the
    session to that connection with join_transaction_mode="create_savepoint".
    Now any commit() the app code does only releases an inner SAVEPOINT; the
    outer transaction stays open and our rollback at the end wipes everything.
    """
    connection = await test_engine.connect()
    transaction = await connection.begin()
    session = AsyncSession(
        bind=connection,
        expire_on_commit=False,
        autoflush=False,
        join_transaction_mode="create_savepoint",
    )
    try:
        yield session
    finally:
        await session.close()
        if transaction.is_active:
            await transaction.rollback()
        await connection.close()


@pytest.fixture
async def client(db_session):
    """httpx client wired to the ASGI app, with get_db pointed at the
    rolled-back test session above."""

    async def _override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = _override_get_db
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.clear()


@pytest.fixture
async def auth_client(client):
    """Same client, but with get_current_user faked — no real login/JWT/Redis.
    Use this for endpoints behind authentication."""

    async def _override_current_user():
        return {"sub": TEST_USER_ID}

    app.dependency_overrides[get_current_user] = _override_current_user
    yield client
    # client's own teardown clears all overrides.


@pytest.fixture(autouse=True)
def _reset_singleton_caches():
    """CommonService caches FareRules/Stations in a module-level singleton that
    would otherwise leak across tests (and get stuck if loaded while empty).
    Reset around every test so each derives fresh from its own seeded DB."""
    common_service._fare_rules_cache = None
    common_service._stations_cache = None
    yield
    common_service._fare_rules_cache = None
    common_service._stations_cache = None


# Journey the seeded world describes: NDLS → BCT on train 12951, SL/GN.
SEED_TRAIN_NUMBER = "12951"
SEED_FROM_STATION = "NDLS"
SEED_TO_STATION = "BCT"
SEED_TRAIN_CLASS = "SL"
SEED_QUOTA = "GN"
SEED_JOURNEY_DATE = date(2026, 12, 1)


def _journey_refs() -> dict:
    """The POST-body references that match the seeded journey."""
    return {
        "train_number": SEED_TRAIN_NUMBER,
        "from_station": SEED_FROM_STATION,
        "to_station": SEED_TO_STATION,
        "train_class": SEED_TRAIN_CLASS,
        "quota": SEED_QUOTA,
        "journey_date": SEED_JOURNEY_DATE.isoformat(),
        "passenger_id": TEST_PASSENGER_ID,
    }


async def _seed_journey_base(session) -> Trains:
    """
    Seed everything a booking needs EXCEPT the seat inventory (and coaches/seats):
    a user, two stations, a train with two stops, a fare rule, and a passenger.
    Returns the Train so callers can attach an inventory tuned to the case.
    """
    session.add(Users(id=TEST_USER_ID, username="tester", email="tester@example.com"))

    src = Stations(
        station_code=SEED_FROM_STATION,
        station_name="New Delhi",
        city="Delhi",
        state="Delhi",
    )
    dst = Stations(
        station_code=SEED_TO_STATION,
        station_name="Mumbai Central",
        city="Mumbai",
        state="Maharashtra",
    )
    session.add_all([src, dst])
    await session.flush()  # need station ids for FKs

    train = Trains(
        train_number=SEED_TRAIN_NUMBER,
        train_name="Test Rajdhani",
        source_station_id=src.id,
        destination_station_id=dst.id,
    )
    session.add(train)
    await session.flush()  # need train.id

    session.add_all(
        [
            TrainStations(
                train_id=train.id,
                station_id=src.id,
                sequence_number=1,
                distance_km=0,
                is_source=True,
            ),
            TrainStations(
                train_id=train.id,
                station_id=dst.id,
                sequence_number=2,
                distance_km=1384,
                is_destination=True,
            ),
        ]
    )
    session.add(
        FareRules(
            train_class=SEED_TRAIN_CLASS,
            base_fare_per_km=0.5,
            reservation_charge=20,
            superfast_min_charge=30,
            tatkal_multiplier=1.3,
            minimum_fare=30,
        )
    )
    session.add(
        Passengers(
            id=TEST_PASSENGER_ID,
            user_id=TEST_USER_ID,
            full_name="Test Passenger",
            age=30,
            gender="MALE",
        )
    )
    return train


@pytest.fixture
async def booking_world(db_session):
    """Seed for a *waitlist* (WL) booking: inventory has zero confirmed/RAC
    seats, so availability resolves to WL — no coaches/seats needed."""
    train = await _seed_journey_base(db_session)
    db_session.add(
        SeatInventories(
            train_id=train.id,
            journey_date=SEED_JOURNEY_DATE,
            train_class=SEED_TRAIN_CLASS,
            quota=SEED_QUOTA,
            total_confirmed_seats=0,
            available_confirmed_seats=0,
        )
    )
    await db_session.flush()
    return _journey_refs()


@pytest.fixture
async def available_world(db_session):
    """Seed for an *AVAILABLE* (confirmed) booking: one coach with two seats and
    an inventory with confirmed seats free. Returns refs plus the inventory id so
    a test can assert the counter was decremented."""
    train = await _seed_journey_base(db_session)

    coach = Coaches(
        train_id=train.id,
        coach_number="S1",
        train_class=SEED_TRAIN_CLASS,
        total_seats=2,
        coach_position=1,
    )
    db_session.add(coach)
    await db_session.flush()  # need coach.id

    db_session.add_all(
        [
            Seats(coach_id=coach.id, seat_number=1, berth_type="LB"),
            Seats(coach_id=coach.id, seat_number=2, berth_type="UB"),
        ]
    )

    inventory = SeatInventories(
        train_id=train.id,
        journey_date=SEED_JOURNEY_DATE,
        train_class=SEED_TRAIN_CLASS,
        quota=SEED_QUOTA,
        total_confirmed_seats=2,
        available_confirmed_seats=2,
    )
    db_session.add(inventory)
    await db_session.flush()

    return {**_journey_refs(), "inventory_id": str(inventory.id)}


# ── Concurrency harness ───────────────────────────────────────────────────────
# The rollback-isolation harness above shares ONE connection, so it can't test a
# real race. These two fixtures use real, independently-committing sessions and
# clean up by truncating afterwards.

# Tables the booking flow touches, child-first isn't needed thanks to CASCADE.
_TRUNCATE_TABLES = [
    "bookings",
    "booking_passengers",
    "waitlists",
    "rac_slots",
    "seat_inventories",
    "seats",
    "coaches",
    "train_stations",
    "trains",
    "stations",
    "passengers",
    "fare_rules",
    "users",
]


async def _truncate_all() -> None:
    qualified = ", ".join(f'"{settings.DB_SCHEMA}".{t}' for t in _TRUNCATE_TABLES)
    async with test_engine.begin() as conn:
        await conn.execute(text(f"TRUNCATE TABLE {qualified} RESTART IDENTITY CASCADE"))


@pytest.fixture
async def racing_client(_test_db):
    """A client whose get_db hands each request its OWN real, committing session
    (production-like) — so two concurrent requests genuinely contend in the DB."""

    async def _override_get_db():
        async with AsyncSession(test_engine, expire_on_commit=False) as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise

    async def _override_current_user():
        return {"sub": TEST_USER_ID}

    app.dependency_overrides[get_db] = _override_get_db
    app.dependency_overrides[get_current_user] = _override_current_user
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.clear()


@pytest.fixture
async def concurrency_world(_test_db):
    """Like single_seat_world, but COMMITTED so independent connections can see
    it. Truncates everything on teardown (no rollback isolation here)."""
    await _truncate_all()  # start from a clean slate
    async with AsyncSession(test_engine, expire_on_commit=False) as session:
        train = await _seed_journey_base(session)
        coach = Coaches(
            train_id=train.id,
            coach_number="S1",
            train_class=SEED_TRAIN_CLASS,
            total_seats=1,
            coach_position=1,
        )
        session.add(coach)
        await session.flush()
        session.add(Seats(coach_id=coach.id, seat_number=1, berth_type="LB"))
        inventory = SeatInventories(
            train_id=train.id,
            journey_date=SEED_JOURNEY_DATE,
            train_class=SEED_TRAIN_CLASS,
            quota=SEED_QUOTA,
            total_confirmed_seats=1,
            available_confirmed_seats=1,
        )
        session.add(inventory)
        await session.commit()
        inventory_id = str(inventory.id)

    yield {**_journey_refs(), "inventory_id": inventory_id}

    await _truncate_all()


@pytest.fixture
async def single_seat_world(db_session):
    """Exactly ONE confirmed seat — to prove the last seat can't be oversold:
    a second booking must fall through to the waitlist instead of double-booking."""
    train = await _seed_journey_base(db_session)

    coach = Coaches(
        train_id=train.id,
        coach_number="S1",
        train_class=SEED_TRAIN_CLASS,
        total_seats=1,
        coach_position=1,
    )
    db_session.add(coach)
    await db_session.flush()

    db_session.add(Seats(coach_id=coach.id, seat_number=1, berth_type="LB"))

    inventory = SeatInventories(
        train_id=train.id,
        journey_date=SEED_JOURNEY_DATE,
        train_class=SEED_TRAIN_CLASS,
        quota=SEED_QUOTA,
        total_confirmed_seats=1,
        available_confirmed_seats=1,
    )
    db_session.add(inventory)
    await db_session.flush()

    return {**_journey_refs(), "inventory_id": str(inventory.id)}
