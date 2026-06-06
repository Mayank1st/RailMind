"""
scripts/seed_seat_data.py

Seeder script — seeds Coaches, Seats, and SeatInventories for all trains.

LOW-MEMORY STREAMING VERSION:
- Records are flushed to DB in chunks as they are generated, instead of
  building millions of dicts in memory first (which OOM-kills on small VMs).
- Periodic commits make the script resumable — re-running safely skips
  already-inserted rows via on_conflict_do_nothing + existing-key checks.

Usage:
    python scripts/seed_seat_data.py
    python scripts/seed_seat_data.py --dry-run
    python scripts/seed_seat_data.py --days 7
"""

import asyncio
import argparse
import sys
import time
import uuid
from datetime import date, timedelta
from pathlib import Path

parser = argparse.ArgumentParser(description="Seed coaches, seats, seat inventories")
parser.add_argument("--batch-size", type=int, default=500)
parser.add_argument("--days", type=int, default=120)
parser.add_argument("--dry-run", action="store_true")
args = parser.parse_args()

BATCH_SIZE = args.batch_size
DAYS_AHEAD = args.days
DRY_RUN = args.dry_run

# Flush thresholds — keep in-memory record lists bounded (low-memory streaming)
SEAT_FLUSH_THRESHOLD = 20_000
INVENTORY_FLUSH_THRESHOLD = 50_000

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_PROJECT_ROOT))

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.db.base import DATABASE_URL, DB_SCHEMA
from app.db.models.train import Coaches, SeatInventories, Seats, Trains
from app.utils.helpers import get_utc_timezone


# ─── Rake Configuration ───────────────────────────────────────────────────────

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

SEAT_CONFIG: dict[str, dict] = {
    "SL": {
        "total_seats": 72,
        "rac_berths": 7,
        "confirmed_seats": 65,
        "berth_layout": [("LB", 18), ("MB", 18), ("UB", 18), ("SL", 11), ("SU", 7)],
    },
    "3A": {
        "total_seats": 64,
        "rac_berths": 4,
        "confirmed_seats": 60,
        "berth_layout": [("LB", 16), ("MB", 16), ("UB", 16), ("SL", 8), ("SU", 8)],
    },
    "2A": {
        "total_seats": 46,
        "rac_berths": 3,
        "confirmed_seats": 43,
        "berth_layout": [("LB", 12), ("UB", 12), ("SL", 8), ("SU", 8), ("LB", 6)],
    },
    "1A": {
        "total_seats": 24,
        "rac_berths": 0,
        "confirmed_seats": 24,
        "berth_layout": [("LB", 12), ("UB", 12)],
    },
    "CC": {
        "total_seats": 78,
        "rac_berths": 0,
        "confirmed_seats": 78,
        "berth_layout": [("SEAT", 78)],
    },
    "2S": {
        "total_seats": 108,
        "rac_berths": 0,
        "confirmed_seats": 108,
        "berth_layout": [("SEAT", 108)],
    },
}

QUOTA_ALLOCATION: dict[str, dict[str, int]] = {
    "SL": {"GN": 70, "TQ": 20, "LD": 3, "HP": 2, "DF": 2, "SS": 2, "FT": 1},
    "3A": {"GN": 70, "TQ": 20, "LD": 2, "HP": 2, "DF": 2, "SS": 3, "FT": 1},
    "2A": {"GN": 70, "TQ": 20, "LD": 2, "HP": 2, "DF": 2, "SS": 3, "FT": 1},
    "1A": {"GN": 70, "TQ": 20, "LD": 0, "HP": 2, "DF": 4, "SS": 3, "FT": 1},
    "CC": {"GN": 75, "TQ": 20, "LD": 2, "HP": 1, "DF": 1, "SS": 1, "FT": 0},
    "2S": {"GN": 80, "TQ": 15, "LD": 2, "HP": 1, "DF": 1, "SS": 1, "FT": 0},
}

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
    if percent == 0:
        return 0
    return max(1, int(confirmed_seats * percent / 100))


def build_berth_sequence(layout, total):
    seats = []
    seat_num = 1
    for berth_type, count in layout:
        for _ in range(count):
            seats.append((seat_num, berth_type, False))
            seat_num += 1
    return seats


def flag_rac_berths(seats, train_class):
    rac_count = RAC_BERTHS_PER_COACH.get(train_class, 0)
    if rac_count == 0:
        return seats
    sl_indexes = [i for i, (_, bt, _) in enumerate(seats) if bt == "SL"]
    rac_indexes = set(sl_indexes[-rac_count:])
    return [(sn, bt, i in rac_indexes) for i, (sn, bt, _) in enumerate(seats)]


# ─── Streaming flush helpers (low-memory) ─────────────────────────────────────


async def _flush_coaches_seats(
    session: AsyncSession,
    coach_records: list,
    seat_records: list,
) -> None:
    """Insert pending coach/seat records, COMMIT, and clear the lists.

    Coaches are inserted before seats (FK dependency). Committing per flush
    keeps the Postgres transaction small and makes the script resumable.
    """
    if coach_records:
        for i in range(0, len(coach_records), BATCH_SIZE):
            stmt = (
                pg_insert(Coaches)
                .values(coach_records[i : i + BATCH_SIZE])
                .on_conflict_do_nothing(index_elements=["train_id", "coach_number"])
            )
            await session.execute(stmt)
        coach_records.clear()

    if seat_records:
        for i in range(0, len(seat_records), BATCH_SIZE):
            stmt = (
                pg_insert(Seats)
                .values(seat_records[i : i + BATCH_SIZE])
                .on_conflict_do_nothing(index_elements=["coach_id", "seat_number"])
            )
            await session.execute(stmt)
        seat_records.clear()

    await session.commit()


async def _flush_inventories(session: AsyncSession, inventory_records: list) -> int:
    """Insert pending inventory records, COMMIT, clear the list. Returns inserted count."""
    inserted = 0
    for i in range(0, len(inventory_records), BATCH_SIZE):
        stmt = (
            pg_insert(SeatInventories)
            .values(inventory_records[i : i + BATCH_SIZE])
            .on_conflict_do_nothing(
                index_elements=["train_id", "journey_date", "train_class", "quota"]
            )
        )
        result = await session.execute(stmt)
        inserted += result.rowcount
    inventory_records.clear()
    await session.commit()
    return inserted


# ─── Seeding functions ────────────────────────────────────────────────────────


async def seed_coaches_and_seats(session: AsyncSession) -> dict:
    print("\n[1/3] Seeding coaches and seats...")

    # Load all trains
    result = await session.execute(
        select(Trains.id, Trains.train_number, Trains.train_type)
    )
    trains = result.fetchall()
    print(f"      Found {len(trains):,} trains")

    # Load existing coaches from DB first (resume-safe)
    existing_result = await session.execute(
        select(Coaches.id, Coaches.train_id, Coaches.coach_number, Coaches.train_class)
    )
    existing_coaches: dict[tuple, uuid.UUID] = {
        (str(row.train_id), row.coach_number): row.id
        for row in existing_result.fetchall()
    }
    print(
        f"      Found {len(existing_coaches):,} coaches already in DB — will skip these"
    )

    coach_records: list = []
    seat_records: list = []
    coach_class_map: dict[str, dict[str, list[uuid.UUID]]] = {}
    total_trains = len(trains)
    coaches_created = 0
    seats_created = 0

    for t_idx, train in enumerate(trains):
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
                coach_number = f"{train_class}{i}"
                existing_key = (str(train_id), coach_number)

                if existing_key in existing_coaches:
                    # Coach already exists — use its real ID
                    coach_id = existing_coaches[existing_key]
                else:
                    # New coach — queue for insert
                    coach_id = new_id()
                    coaches_created += 1
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

                    # Build seats only for new coaches
                    raw_seats = build_berth_sequence(
                        seat_cfg["berth_layout"], seat_cfg["total_seats"]
                    )
                    seats_with_rac = flag_rac_berths(raw_seats, train_class)

                    for seat_num, berth_type, is_rac in seats_with_rac:
                        seats_created += 1
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

        # ── STREAMING FLUSH: keep memory bounded ──────────────────────────────
        if len(seat_records) >= SEAT_FLUSH_THRESHOLD:
            await _flush_coaches_seats(session, coach_records, seat_records)
            pct = int((t_idx + 1) / total_trains * 100)
            print(
                f"\r      Progress: {pct}%  ({t_idx + 1:,}/{total_trains:,} trains, "
                f"{seats_created:,} seats so far)",
                end="",
                flush=True,
            )

    # Final flush of any remainder
    await _flush_coaches_seats(session, coach_records, seat_records)

    if coaches_created:
        print(
            f"\r      Coaches: {coaches_created:,} new, "
            f"Seats: {seats_created:,} new — done ✅                    "
        )
    else:
        print("      All coaches/seats already exist — skipped ✅")

    return coach_class_map


async def seed_seat_inventories(session: AsyncSession, coach_class_map: dict) -> None:
    print(f"\n[2/3] Seeding seat inventories ({DAYS_AHEAD} days ahead)...")

    # Load existing inventory keys from DB (resume-safe)
    existing_inv_result = await session.execute(
        select(
            SeatInventories.train_id,
            SeatInventories.journey_date,
            SeatInventories.train_class,
            SeatInventories.quota,
        )
    )
    existing_inv_keys: set[tuple] = {
        (str(row.train_id), str(row.journey_date), row.train_class, row.quota)
        for row in existing_inv_result.fetchall()
    }
    print(
        f"      Found {len(existing_inv_keys):,} inventory rows already in DB — will skip these"
    )

    today = date.today()
    date_range = [today + timedelta(days=d) for d in range(DAYS_AHEAD + 1)]

    inventory_records: list = []
    total_trains = len(coach_class_map)
    total_inserted = 0

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

                    # Skip if already exists
                    inv_key = (train_id_str, str(journey_date), train_class, quota)
                    if inv_key in existing_inv_keys:
                        continue

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

        # ── STREAMING FLUSH: keep memory bounded ──────────────────────────────
        if len(inventory_records) >= INVENTORY_FLUSH_THRESHOLD:
            total_inserted += await _flush_inventories(session, inventory_records)

        pct = int((t_idx + 1) / total_trains * 100)
        print(
            f"\r      Progress: {pct}%  ({t_idx + 1:,}/{total_trains:,} trains, "
            f"{total_inserted:,} rows inserted)",
            end="",
            flush=True,
        )

    # Final flush of any remainder
    if inventory_records:
        total_inserted += await _flush_inventories(session, inventory_records)

    if total_inserted:
        print(
            f"\r      Inventories: {total_inserted:,} new inserted ✅                    "
        )
    else:
        print("\r      All inventories already exist — skipped ✅                    ")


# ─── Main ─────────────────────────────────────────────────────────────────────


async def main() -> None:
    start_time = time.time()

    print("=" * 60)
    print("  RailMind — Seat Data Seeder (streaming)")
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
                f"  {train_type:<15} coaches={total_coaches:>3}  seats={total_seats:>5}  inventory_rows/train={inv_rows:>5}"
            )
        return

    engine = create_async_engine(
        DATABASE_URL,
        echo=False,
        pool_size=5,
        max_overflow=10,
        connect_args={"server_settings": {"search_path": f'"{DB_SCHEMA}"'}},
    )
    async_session = async_sessionmaker(
        bind=engine, class_=AsyncSession, expire_on_commit=False
    )

    # NOTE: no single wrapping transaction — flush helpers commit periodically.
    # Combined with on_conflict_do_nothing + existing-key checks, the script is
    # safe to re-run and resumes where it left off.
    async with async_session() as session:
        try:
            coach_class_map = await seed_coaches_and_seats(session)
            print(f"\n[3/3] Coach map built for {len(coach_class_map):,} trains")
            await seed_seat_inventories(session, coach_class_map)
        except Exception as e:
            await session.rollback()
            print(f"\n[ERROR] {e}")
            raise

    await engine.dispose()

    elapsed = time.time() - start_time
    print(f"\n{'=' * 60}")
    print(f"  Seeding complete in {elapsed:.1f}s")
    print(f"{'=' * 60}\n")


if __name__ == "__main__":
    asyncio.run(main())
