"""
Docstring for scripts.seed_seat_data

How to Run

DRY RUN : python scripts/seed_seat_data.py --dry-run
ACTUAL EXECUTION : python scripts/seed_seat_data.py
"""

import asyncio
import argparse
import sys
import time
import uuid
from datetime import date, timedelta
from pathlib import Path

# ─── Args ─────────────────────────────────────────────────────────────────────

parser = argparse.ArgumentParser(description="Seed coaches, seats, seat inventories")
parser.add_argument(
    "--batch-size", type=int, default=500, help="Insert batch size (default: 500)"
)
parser.add_argument(
    "--days", type=int, default=120, help="Days ahead to seed inventory (default: 120)"
)
parser.add_argument(
    "--dry-run", action="store_true", help="Parse only — do not write to DB"
)
args = parser.parse_args()

BATCH_SIZE = args.batch_size
DAYS_AHEAD = args.days
DRY_RUN = args.dry_run

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_PROJECT_ROOT))

from sqlalchemy import select, text
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.db.base import DATABASE_URL, DB_SCHEMA
from app.db.models.train import Coaches, SeatInventories, Seats, Trains
from app.utils.helpers import get_utc_timezone


# ─── Rake Configuration ───────────────────────────────────────────────────────
# Number of coaches per class for each train type.
# Based on standard Indian Railways ICF/LHB rake composition.
# Key: train_type value, Value: dict of {train_class: coach_count}

RAKE_CONFIG: dict[str, dict[str, int]] = {
    "rajdhani": {"3A": 12, "2A": 4, "1A": 2},
    "shatabdi": {"CC": 12, "2S": 2},
    "jan_shatabdi": {"CC": 8, "2S": 4},
    "duronto": {"SL": 2, "3A": 10, "2A": 4, "1A": 2},
    "garib_rath": {"3A": 14},
    "superfast": {"SL": 8, "3A": 4, "2A": 2, "1A": 1, "2S": 2},
    "express": {"SL": 10, "3A": 2, "2A": 2, "2S": 2},
    "passenger": {"2S": 16},
    "suburban": {"2S": 12},
    "demu": {"2S": 8},
    "special": {"SL": 6, "3A": 2, "2A": 1},
    "heritage": {"2S": 6},
    "unknown": {"SL": 6, "3A": 2, "2A": 1},
}

# ─── Seat Configuration per Coach Class ───────────────────────────────────────
# total_seats     — physical berths in one coach
# rac_berths      — side-lower berths earmarked for RAC (never sold as CNF)
# confirmed_seats — total_seats - rac_berths (what goes into quota pool)
# berth_layout    — list of (berth_type, count) tuples

SEAT_CONFIG: dict[str, dict] = {
    "SL": {
        "total_seats": 72,
        "rac_berths": 7,
        "confirmed_seats": 65,
        # 8 bays × (LB+MB+UB+SL+SU) = 8×5=40... actually SL has 8 bays of 8 = 64 + 8 side
        # Standard: 8 bays × (LB, MB, UB, SL, SU, LB, MB, UB) → simplified layout:
        "berth_layout": [
            ("LB", 18),
            ("MB", 18),
            ("UB", 18),  # main bays
            ("SL", 11),
            ("SU", 7),  # side berths (7 are RAC)
        ],
    },
    "3A": {
        "total_seats": 64,
        "rac_berths": 4,
        "confirmed_seats": 60,
        "berth_layout": [
            ("LB", 16),
            ("MB", 16),
            ("UB", 16),
            ("SL", 8),
            ("SU", 8),
        ],
    },
    "2A": {
        "total_seats": 46,
        "rac_berths": 3,
        "confirmed_seats": 43,
        "berth_layout": [
            ("LB", 12),
            ("UB", 12),
            ("SL", 8),
            ("SU", 8),
            ("LB", 6),  # extra lower berths
        ],
    },
    "1A": {
        "total_seats": 24,
        "rac_berths": 0,
        "confirmed_seats": 24,
        "berth_layout": [
            ("LB", 12),
            ("UB", 12),
        ],
    },
    "CC": {
        "total_seats": 78,
        "rac_berths": 0,
        "confirmed_seats": 78,
        "berth_layout": [
            ("SEAT", 78),
        ],
    },
    "2S": {
        "total_seats": 108,
        "rac_berths": 0,
        "confirmed_seats": 108,
        "berth_layout": [
            ("SEAT", 108),
        ],
    },
}

# ─── Quota Allocation ─────────────────────────────────────────────────────────
# Percentage of confirmed_seats allocated to each quota per class.
# Must sum to 100 per class.
# GN gets the remainder after all special quotas are allocated.

QUOTA_ALLOCATION: dict[str, dict[str, int]] = {
    #          GN   TQ   LD   HP   DF   SS   FT
    "SL": {"GN": 70, "TQ": 20, "LD": 3, "HP": 2, "DF": 2, "SS": 2, "FT": 1},
    "3A": {"GN": 70, "TQ": 20, "LD": 2, "HP": 2, "DF": 2, "SS": 3, "FT": 1},
    "2A": {"GN": 70, "TQ": 20, "LD": 2, "HP": 2, "DF": 2, "SS": 3, "FT": 1},
    "1A": {"GN": 70, "TQ": 20, "LD": 0, "HP": 2, "DF": 4, "SS": 3, "FT": 1},
    "CC": {"GN": 75, "TQ": 20, "LD": 2, "HP": 1, "DF": 1, "SS": 1, "FT": 0},
    "2S": {"GN": 80, "TQ": 15, "LD": 2, "HP": 1, "DF": 1, "SS": 1, "FT": 0},
}

# WL max depth per quota type
WL_MAX: dict[str, int] = {
    "GN": 200,
    "TQ": 50,
    "PT": 50,
    "LD": 20,
    "HP": 20,
    "DF": 20,
    "SS": 20,
    "FT": 10,
}

# ─── RAC berths config (from constants) ───────────────────────────────────────
RAC_BERTHS_PER_COACH: dict[str, int] = {
    "SL": 7,
    "3A": 4,
    "2A": 3,
    "1A": 0,
    "CC": 0,
    "2S": 0,
    "FC": 0,
    "3E": 2,
}


# ─── Helpers ──────────────────────────────────────────────────────────────────


def new_id() -> uuid.UUID:
    return uuid.uuid4()


def now_utc():
    return get_utc_timezone()


def calc_quota_seats(confirmed_seats: int, percent: int) -> int:
    """Floor division — minimum 1 seat if percent > 0."""
    if percent == 0:
        return 0
    seats = int(confirmed_seats * percent / 100)
    return max(1, seats)


def build_berth_sequence(
    layout: list[tuple[str, int]], total: int
) -> list[tuple[int, str, bool]]:
    """
    Returns list of (seat_number, berth_type, is_rac_berth).
    Last N side-lower berths are flagged as RAC berths.
    N = RAC_BERTHS_PER_COACH for this class (passed in via layout total check).
    """
    seats = []
    seat_num = 1
    for berth_type, count in layout:
        for _ in range(count):
            seats.append((seat_num, berth_type, False))
            seat_num += 1
    return seats


def flag_rac_berths(
    seats: list[tuple[int, str, bool]],
    train_class: str,
) -> list[tuple[int, str, bool]]:
    """
    Mark the last N side-lower berths as RAC berths.
    Side-lower berths are identified by berth_type = "SL".
    """
    rac_count = RAC_BERTHS_PER_COACH.get(train_class, 0)
    if rac_count == 0:
        return seats

    # Find all SL berth indexes (0-based in list)
    sl_indexes = [i for i, (_, bt, _) in enumerate(seats) if bt == "SL"]

    # Flag the last rac_count of them as RAC berths
    rac_indexes = set(sl_indexes[-rac_count:])

    return [(sn, bt, i in rac_indexes) for i, (sn, bt, _) in enumerate(seats)]


# ─── Main seeding functions ───────────────────────────────────────────────────


async def seed_coaches_and_seats(session: AsyncSession) -> dict[str, list[uuid.UUID]]:
    """
    Seed Coaches and Seats for all trains.

    Returns:
        coach_class_map: {train_id_str: {train_class: [coach_id, ...]}}
    """
    print("\n[1/3] Seeding coaches and seats...")

    # Load all trains
    result = await session.execute(
        select(Trains.id, Trains.train_number, Trains.train_type)
    )
    trains = result.fetchall()
    print(f"      Found {len(trains):,} trains to process")

    coach_records = []
    seat_records = []
    # train_id → class → list of coach_ids (for inventory seeding)
    coach_class_map: dict[str, dict[str, list[uuid.UUID]]] = {}

    for train in trains:
        train_id = train.id
        train_type = train.train_type or "unknown"
        rake = RAKE_CONFIG.get(train_type, RAKE_CONFIG["unknown"])

        coach_class_map[str(train_id)] = {}

        position = 1
        for train_class, coach_count in rake.items():
            if train_class not in SEAT_CONFIG:
                continue

            seat_cfg = SEAT_CONFIG[train_class]
            coach_ids_for_class = []

            for i in range(1, coach_count + 1):
                coach_id = new_id()
                coach_number = f"{train_class}{i}"  # e.g. SL1, 3A1, CC1

                coach_records.append(
                    {
                        "id": coach_id,
                        "train_id": train_id,
                        "coach_number": coach_number,
                        "train_class": train_class,
                        "total_seats": seat_cfg["total_seats"],
                        "is_ac": train_class in ("1A", "2A", "3A", "CC", "3E"),
                        "coach_position": position,
                        "is_active": True,
                        "created_at": now_utc(),
                        "updated_at": now_utc(),
                    }
                )

                # Build seat rows for this coach
                raw_seats = build_berth_sequence(
                    seat_cfg["berth_layout"],
                    seat_cfg["total_seats"],
                )
                seats_with_rac = flag_rac_berths(raw_seats, train_class)

                for seat_num, berth_type, is_rac in seats_with_rac:
                    seat_records.append(
                        {
                            "id": new_id(),
                            "coach_id": coach_id,
                            "seat_number": seat_num,
                            "berth_type": berth_type,
                            "is_rac_berth": is_rac,
                            "is_active": True,
                            "created_at": now_utc(),
                            "updated_at": now_utc(),
                        }
                    )

                coach_ids_for_class.append(coach_id)
                position += 1

            coach_class_map[str(train_id)][train_class] = coach_ids_for_class

    # ── Batch insert coaches ──────────────────────────────────────────────────
    print(f"      Inserting {len(coach_records):,} coaches...")
    inserted_coaches = 0
    for i in range(0, len(coach_records), BATCH_SIZE):
        batch = coach_records[i : i + BATCH_SIZE]
        stmt = (
            pg_insert(Coaches)
            .values(batch)
            .on_conflict_do_nothing(index_elements=["train_id", "coach_number"])
        )
        result = await session.execute(stmt)
        inserted_coaches += result.rowcount

    skipped_coaches = len(coach_records) - inserted_coaches
    print(
        f"      Coaches: {inserted_coaches:,} new, {skipped_coaches:,} already existed ✅"
    )

    # ── Batch insert seats ────────────────────────────────────────────────────
    print(f"      Inserting {len(seat_records):,} seats (this takes a moment)...")
    inserted_seats = 0
    total_seats = len(seat_records)
    for i in range(0, total_seats, BATCH_SIZE):
        batch = seat_records[i : i + BATCH_SIZE]
        stmt = (
            pg_insert(Seats)
            .values(batch)
            .on_conflict_do_nothing(index_elements=["coach_id", "seat_number"])
        )
        result = await session.execute(stmt)
        inserted_seats += result.rowcount
        pct = int((i + len(batch)) / total_seats * 100)
        print(
            f"\r      Seats progress: {pct}%  ({i + len(batch):,}/{total_seats:,})",
            end="",
            flush=True,
        )

    skipped_seats = len(seat_records) - inserted_seats
    print(
        f"\r      Seats: {inserted_seats:,} new, {skipped_seats:,} already existed ✅          "
    )

    return coach_class_map


async def seed_seat_inventories(
    session: AsyncSession,
    coach_class_map: dict[str, dict[str, list[uuid.UUID]]],
) -> None:
    """
    Seed SeatInventories for all trains × all dates × all classes × all quotas.
    """
    print(f"\n[2/3] Seeding seat inventories ({DAYS_AHEAD} days ahead)...")

    today = date.today()
    date_range = [today + timedelta(days=d) for d in range(DAYS_AHEAD + 1)]

    inventory_records = []
    total_trains = len(coach_class_map)

    for t_idx, (train_id_str, class_map) in enumerate(coach_class_map.items()):
        train_id = uuid.UUID(train_id_str)

        for train_class, coach_ids in class_map.items():
            if train_class not in SEAT_CONFIG:
                continue

            seat_cfg = SEAT_CONFIG[train_class]
            coach_count = len(coach_ids)
            confirmed_seats = seat_cfg["confirmed_seats"] * coach_count
            rac_berths = RAC_BERTHS_PER_COACH.get(train_class, 0) * coach_count
            rac_slots = rac_berths * 2

            quota_alloc = QUOTA_ALLOCATION.get(train_class, QUOTA_ALLOCATION["SL"])

            for journey_date in date_range:
                for quota, percent in quota_alloc.items():
                    quota_seats = calc_quota_seats(confirmed_seats, percent)
                    if quota_seats == 0:
                        continue

                    # RAC only applies to GN quota
                    inv_rac_berths = rac_berths if quota == "GN" else 0
                    inv_rac_slots = rac_slots if quota == "GN" else 0

                    inventory_records.append(
                        {
                            "id": new_id(),
                            "train_id": train_id,
                            "journey_date": journey_date,
                            "train_class": train_class,
                            "quota": quota,
                            "total_confirmed_seats": quota_seats,
                            "available_confirmed_seats": quota_seats,
                            "total_rac_berths": inv_rac_berths,
                            "total_rac_slots": inv_rac_slots,
                            "available_rac_slots": inv_rac_slots,
                            "wl_count": 0,
                            "wl_max": WL_MAX.get(quota, 100),
                            "is_chart_prepared": False,
                            "chart_prepared_at": None,
                            "quota_released_seats": 0,
                            "is_active": True,
                            "created_at": now_utc(),
                            "updated_at": now_utc(),
                        }
                    )

        # Progress per train
        pct = int((t_idx + 1) / total_trains * 100)
        print(
            f"\r      Building records: {pct}%  ({t_idx + 1:,}/{total_trains:,} trains)",
            end="",
            flush=True,
        )

    print(
        f"\r      Built {len(inventory_records):,} inventory records                              "
    )

    # ── Batch insert inventories ──────────────────────────────────────────────
    print(f"      Inserting into DB (this is the big one)...")
    inserted = 0
    total = len(inventory_records)

    for i in range(0, total, BATCH_SIZE):
        batch = inventory_records[i : i + BATCH_SIZE]
        stmt = (
            pg_insert(SeatInventories)
            .values(batch)
            .on_conflict_do_nothing(
                index_elements=["train_id", "journey_date", "train_class", "quota"]
            )
        )
        result = await session.execute(stmt)
        inserted += result.rowcount
        pct = int((i + len(batch)) / total * 100)
        print(
            f"\r      Inventory progress: {pct}%  ({i + len(batch):,}/{total:,})",
            end="",
            flush=True,
        )

    skipped = total - inserted
    print(
        f"\r      Inventories: {inserted:,} new, {skipped:,} already existed ✅          "
    )


# ─── Main ─────────────────────────────────────────────────────────────────────


async def main() -> None:
    start_time = time.time()

    print("=" * 60)
    print("  RailMind — Seat Data Seeder")
    print("=" * 60)
    print(f"  Days ahead:  {DAYS_AHEAD}")
    print(f"  Batch size:  {BATCH_SIZE}")
    print(f"  Dry run:     {DRY_RUN}")
    print("=" * 60)

    if DRY_RUN:
        print("\n[DRY RUN] Showing what would be seeded:\n")
        for train_type, rake in RAKE_CONFIG.items():
            total_coaches = sum(rake.values())
            total_seats = sum(
                SEAT_CONFIG[c]["total_seats"] * count
                for c, count in rake.items()
                if c in SEAT_CONFIG
            )
            quota_rows = sum(
                len(QUOTA_ALLOCATION.get(c, {})) for c in rake if c in SEAT_CONFIG
            )
            inv_rows = quota_rows * (DAYS_AHEAD + 1)
            print(
                f"  {train_type:<15} "
                f"coaches={total_coaches:>3}  "
                f"seats={total_seats:>5}  "
                f"inventory_rows/train={inv_rows:>5}"
            )
        print(f"\n  Total trains in DB would each get the above × their type")
        return

    engine = create_async_engine(
        DATABASE_URL,
        echo=False,
        pool_size=5,
        max_overflow=10,
        connect_args={"server_settings": {"search_path": f'"{DB_SCHEMA}"'}},
    )

    async_session = async_sessionmaker(
        bind=engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )

    async with async_session() as session:
        async with session.begin():
            try:
                coach_class_map = await seed_coaches_and_seats(session)
                print(f"\n[3/3] Coach map built for {len(coach_class_map):,} trains")
                await seed_seat_inventories(session, coach_class_map)
            except Exception as e:
                print(f"\n[ERROR] {e}")
                raise

    await engine.dispose()

    elapsed = time.time() - start_time
    print(f"\n{'=' * 60}")
    print(f"  Seeding complete in {elapsed:.1f}s")
    print(f"{'=' * 60}\n")


if __name__ == "__main__":
    asyncio.run(main())
