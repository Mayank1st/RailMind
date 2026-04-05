"""
scripts/seed_train_data.py

Seeder script — loads Indian Railways CSV into railmind_db.

Tables populated:
  1. stations       (8,151 unique stations)
  2. trains         (11,113 unique trains)
  3. train_stations (186,119 stop records)

Usage:
    python scripts/seed_train_data.py --csv Train_details_22122017.csv
    python scripts/seed_train_data.py --csv data/Train_details_22122017.csv
    python scripts/seed_train_data.py --csv /absolute/path/to/file.csv --batch-size 500
    python scripts/seed_train_data.py --csv Train_details_22122017.csv --dry-run

The CSV is searched as: exact path → project root / path → project root / data / filename.
Download the Indian Railways train-details CSV and place it under ./data/ (gitignored).
"""

import asyncio
import argparse
import sys
import time
from pathlib import Path
from datetime import datetime

import pandas as pd
import uuid

# ─── Args ─────────────────────────────────────────────────────────────────────

parser = argparse.ArgumentParser(description="Seed train data from CSV into railmind_db")
parser.add_argument("--csv",        required=True,       help="Path to CSV file")
parser.add_argument("--batch-size", type=int, default=500, help="Insert batch size (default: 500)")
parser.add_argument("--dry-run",    action="store_true", help="Parse only — do not write to DB")
args = parser.parse_args()

BATCH_SIZE = args.batch_size
DRY_RUN    = args.dry_run

_PROJECT_ROOT = Path(__file__).resolve().parent.parent


def _resolve_csv_path(arg: str) -> Path:
    p = Path(arg).expanduser()
    if p.is_file():
        return p.resolve()
    name = p.name if p.parts else arg
    rel = Path(arg)
    for candidate in (
        _PROJECT_ROOT / rel,
        _PROJECT_ROOT / "data" / name,
        _PROJECT_ROOT / "data" / rel,
        _PROJECT_ROOT / name,
    ):
        if candidate.is_file():
            return candidate.resolve()
    return (_PROJECT_ROOT / rel).resolve()


CSV_PATH = _resolve_csv_path(args.csv)

if not CSV_PATH.is_file():
    print(f"[ERROR] CSV not found: {args.csv}")
    print(f"        Tried (among others): {_PROJECT_ROOT / 'data' / Path(args.csv).name}")
    print(f"        Put the file in the project root or in ./data/ and pass --csv again.")
    sys.exit(1)


# ─── DB Setup ─────────────────────────────────────────────────────────────────

# Add project root to path so app imports work
sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy import text, select
from app.config import settings
from app.db.base import DATABASE_URL, DB_SCHEMA
from app.db.models.train import Stations, TrainStations, Trains
from app.utils.helpers import get_utc_timezone


# ─── Helpers ──────────────────────────────────────────────────────────────────

def parse_time(val: str) -> str | None:
    """
    Return time string as-is if valid, None if it's 00:00:00 (used as null marker in CSV).
    Source station arrival = None, destination departure = None.
    """
    if not val or str(val).strip() == "00:00:00":
        return None
    return str(val).strip()


def calc_halt_minutes(arrival: str | None, departure: str | None) -> int:
    """
    Calculate halt time in minutes from arrival and departure strings.
    Returns 0 if either is None (source/destination stations).
    """
    if not arrival or not departure:
        return 0
    try:
        fmt = "%H:%M:%S"
        arr = datetime.strptime(arrival, fmt)
        dep = datetime.strptime(departure, fmt)
        diff = (dep - arr).seconds // 60
        # handle overnight (negative diff means crosses midnight)
        if diff < 0:
            diff += 24 * 60
        return diff
    except Exception:
        return 0


def new_id() -> uuid.UUID:
    return uuid.uuid4()


def now_utc():
    # Match app DB columns: TIMESTAMP WITHOUT TIME ZONE + naive UTC
    return get_utc_timezone()


# ─── CSV Loading & Cleaning ───────────────────────────────────────────────────

def load_and_clean_csv(path: Path) -> pd.DataFrame:
    print(f"\n[1/5] Reading CSV: {path}")
    df = pd.read_csv(
        path,
        dtype={
            "Train No":   str,
            "SEQ":        str,
            "Distance":   str,
        },
        low_memory=False,
    )

    total_before = len(df)
    print(f"      Raw rows: {total_before:,}")

    # ── Filter bad rows ────────────────────────────────────────────────────────
    # Bad rows have Train No = 'K' or non-numeric Train No
    df = df[df["Train No"].str.match(r"^\d+$", na=False)]

    # Filter rows with NaN distance
    df = df[df["Distance"].str.match(r"^\d+$", na=False)]

    # Strip whitespace from all string columns
    str_cols = df.select_dtypes(include="object").columns
    df[str_cols] = df[str_cols].apply(lambda col: col.str.strip())

    total_after = len(df)
    print(f"      Clean rows: {total_after:,}  (removed {total_before - total_after} bad rows)")

    # Cast numeric columns
    df["Train No"] = df["Train No"].astype(int)
    df["SEQ"]      = df["SEQ"].astype(int)
    df["Distance"] = df["Distance"].astype(int)

    return df


# ─── Data Extraction ──────────────────────────────────────────────────────────

def extract_stations(df: pd.DataFrame) -> pd.DataFrame:
    """
    Extract all unique stations from both stop stations AND
    source/destination station columns.
    """
    print("\n[2/5] Extracting unique stations...")

    # From stop stations (Station Code + Station Name)
    stops = df[["Station Code", "Station Name"]].drop_duplicates()
    stops.columns = ["station_code", "station_name"]

    # From source stations
    src = df[["Source Station", "Source Station Name"]].drop_duplicates()
    src.columns = ["station_code", "station_name"]

    # From destination stations
    dst = df[["Destination Station", "Destination Station Name"]].drop_duplicates()
    dst.columns = ["station_code", "station_name"]

    # Merge all — deduplicate by station_code
    all_stations = (
        pd.concat([stops, src, dst])
        .drop_duplicates(subset=["station_code"])
        .reset_index(drop=True)
    )

    print(f"      Unique stations: {len(all_stations):,}")
    return all_stations


def extract_trains(df: pd.DataFrame) -> pd.DataFrame:
    """
    Extract unique trains — one row per train number.
    """
    print("\n[3/5] Extracting unique trains...")

    trains = (
        df[[
            "Train No", "Train Name",
            "Source Station", "Destination Station"
        ]]
        .drop_duplicates(subset=["Train No"])
        .reset_index(drop=True)
    )
    trains.columns = [
        "train_number", "train_name",
        "source_station_code", "destination_station_code"
    ]

    print(f"      Unique trains: {len(trains):,}")
    return trains


def extract_stops(df: pd.DataFrame) -> pd.DataFrame:
    """
    Extract all train stop records with timing info.
    """
    print("\n[4/5] Extracting train stops...")

    stops = df[[
        "Train No", "SEQ", "Station Code",
        "Arrival time", "Departure Time", "Distance"
    ]].copy()

    stops.columns = [
        "train_number", "sequence_number", "station_code",
        "arrival_raw", "departure_raw", "distance_km"
    ]

    print(f"      Total stops: {len(stops):,}")
    return stops


# ─── DB Insertion ─────────────────────────────────────────────────────────────

async def insert_stations(
    session: AsyncSession,
    stations_df: pd.DataFrame,
) -> dict[str, uuid.UUID]:
    """
    Insert all stations. Returns {station_code: uuid} map.
    """
    print("\n      Inserting stations...", end="", flush=True)

    station_map: dict[str, uuid.UUID] = {}
    records = []

    for _, row in stations_df.iterrows():
        sid = new_id()
        station_map[row["station_code"]] = sid
        records.append(
            Stations(
                id=sid,
                station_code=row["station_code"],
                station_name=row["station_name"],
                created_at=now_utc(),
                updated_at=now_utc(),
            )
        )

    # Batch insert
    for i in range(0, len(records), BATCH_SIZE):
        batch = records[i : i + BATCH_SIZE]
        session.add_all(batch)
        await session.flush()

    print(f" {len(records):,} inserted ✅")
    return station_map


async def insert_trains(
    session: AsyncSession,
    trains_df: pd.DataFrame,
    station_map: dict[str, uuid.UUID],
) -> dict[int, uuid.UUID]:
    """
    Insert all trains. Returns {train_number: uuid} map.
    """
    print("      Inserting trains...", end="", flush=True)

    train_map: dict[int, uuid.UUID] = {}
    records = []
    skipped = 0

    for _, row in trains_df.iterrows():
        src_id = station_map.get(row["source_station_code"])
        dst_id = station_map.get(row["destination_station_code"])

        if not src_id or not dst_id:
            skipped += 1
            continue

        tid = new_id()
        train_map[row["train_number"]] = tid
        records.append(
            Trains(
                id=tid,
                train_number=str(row["train_number"]),
                train_name=row["train_name"],
                source_station_id=src_id,
                destination_station_id=dst_id,
                is_active=True,
                created_at=now_utc(),
                updated_at=now_utc(),
            )
        )

    for i in range(0, len(records), BATCH_SIZE):
        batch = records[i : i + BATCH_SIZE]
        session.add_all(batch)
        await session.flush()

    print(f" {len(records):,} inserted (skipped {skipped}) ✅")
    return train_map


async def insert_stops(
    session: AsyncSession,
    stops_df: pd.DataFrame,
    train_map: dict[int, uuid.UUID],
    station_map: dict[str, uuid.UUID],
) -> None:
    """
    Insert all train_stations records in batches.
    """
    print("      Inserting train stops (this takes ~30s)...")

    records = []
    skipped = 0

    for _, row in stops_df.iterrows():
        train_id   = train_map.get(row["train_number"])
        station_id = station_map.get(row["station_code"])

        if not train_id or not station_id:
            skipped += 1
            continue

        arrival   = parse_time(row["arrival_raw"])
        departure = parse_time(row["departure_raw"])
        halt      = calc_halt_minutes(arrival, departure)

        records.append(
            TrainStations(
                id=new_id(),
                train_id=train_id,
                station_id=station_id,
                sequence_number=int(row["sequence_number"]),
                arrival_time=arrival,
                departure_time=departure,
                distance_km=int(row["distance_km"]),
                halt_minutes=halt,
                is_source=(int(row["sequence_number"]) == 1),
                is_destination=(departure is None and arrival is not None),
                created_at=now_utc(),
                updated_at=now_utc(),
            )
        )

    # Insert in batches — show progress
    total   = len(records)
    batches = range(0, total, BATCH_SIZE)

    for i, start in enumerate(batches):
        batch = records[start : start + BATCH_SIZE]
        session.add_all(batch)
        await session.flush()

        pct = int((start + len(batch)) / total * 100)
        print(f"\r      Progress: {pct}%  ({start + len(batch):,}/{total:,})", end="", flush=True)

    print(f"\r      {total:,} stops inserted (skipped {skipped}) ✅          ")


# ─── Main ─────────────────────────────────────────────────────────────────────

async def main():
    start = time.time()

    print("=" * 60)
    print("  RailMind — Train Data Seeder")
    print("=" * 60)
    print(f"  CSV:        {CSV_PATH}")
    print(f"  Batch size: {BATCH_SIZE}")
    print(f"  Dry run:    {DRY_RUN}")
    print("=" * 60)

    # ── Step 1-4: Load and parse CSV ──────────────────────────────────────────
    df           = load_and_clean_csv(CSV_PATH)
    stations_df  = extract_stations(df)
    trains_df    = extract_trains(df)
    stops_df     = extract_stops(df)

    if DRY_RUN:
        print("\n[DRY RUN] Parsing complete. No data written to DB.")
        print(f"  Would insert {len(stations_df):,} stations")
        print(f"  Would insert {len(trains_df):,} trains")
        print(f"  Would insert {len(stops_df):,} stops")
        return

    # ── Step 5: Insert into DB ────────────────────────────────────────────────
    print("\n[5/5] Inserting into railmind_db...")

    engine = create_async_engine(
        DATABASE_URL,
        echo=False,
        pool_size=5,
        max_overflow=10,
        connect_args={
            "server_settings": {"search_path": f'"{DB_SCHEMA}"'},
        },
    )

    async_session = async_sessionmaker(
        bind=engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )

    async with async_session() as session:
        async with session.begin():
            try:
                # Check if already seeded
                result = await session.execute(
                    text(f'SELECT COUNT(*) FROM "{DB_SCHEMA}".trains')
                )
                count = result.scalar()
                if count > 0:
                    print(f"\n[WARNING] trains table already has {count:,} rows.")
                    confirm = input("  Continue and add more? (y/N): ").strip().lower()
                    if confirm != "y":
                        print("  Aborted.")
                        return

                # Insert in order — stations first (FK dependency)
                station_map = await insert_stations(session, stations_df)
                train_map   = await insert_trains(session, trains_df, station_map)
                await insert_stops(session, stops_df, train_map, station_map)

            except Exception as e:
                print(f"\n[ERROR] {e}")
                raise

    await engine.dispose()

    elapsed = time.time() - start
    print(f"\n{'=' * 60}")
    print(f"  Seeding complete in {elapsed:.1f}s")
    print(f"  Stations : {len(stations_df):,}")
    print(f"  Trains   : {len(trains_df):,}")
    print(f"  Stops    : {len(stops_df):,}")
    print(f"{'=' * 60}\n")


if __name__ == "__main__":
    asyncio.run(main())