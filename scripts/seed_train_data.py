import asyncio
import argparse
import sys
import time
from pathlib import Path
from datetime import datetime

import pandas as pd
import uuid

# ─── Args ─────────────────────────────────────────────────────────────────────

parser = argparse.ArgumentParser(
    description="Seed train data from CSV into railmind_db"
)
parser.add_argument("--csv", required=True, help="Path to CSV file")
parser.add_argument(
    "--batch-size", type=int, default=500, help="Insert batch size (default: 500)"
)
parser.add_argument(
    "--dry-run", action="store_true", help="Parse only — do not write to DB"
)
args = parser.parse_args()

BATCH_SIZE = args.batch_size
DRY_RUN = args.dry_run

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
    print(f"        Put the file in ./data/ and pass --csv again.")
    sys.exit(1)

# ─── Project imports ──────────────────────────────────────────────────────────

sys.path.insert(0, str(_PROJECT_ROOT))

from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy import text, select
from app.db.base import DATABASE_URL, DB_SCHEMA
from app.db.models.train import Stations, Trains, TrainStations
from app.utils.helpers import get_utc_timezone


# ─── Constants ────────────────────────────────────────────────────────────────

ALL_DAYS = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]


# ─── Train Type Derivation ────────────────────────────────────────────────────


def derive_train_type(train_name: str, train_number: int) -> str:
    name = train_name.upper()
    n = int(train_number)

    if "RAJDHANI" in name:
        return "rajdhani"
    if "JANSHATABDI" in name:
        return "jan_shatabdi"
    if "JAN SHATABDI" in name:
        return "jan_shatabdi"
    if "SHATABDI" in name:
        return "shatabdi"
    if "DURONTO" in name:
        return "duronto"
    if "HUMSAFAR" in name:
        return "superfast"
    if "VANDE BHARAT" in name:
        return "superfast"
    if "GATIMAAN" in name:
        return "superfast"
    if "TEJAS" in name:
        return "superfast"
    if "ANTYODAYA" in name:
        return "superfast"
    if "GARIBRATH" in name:
        return "garib_rath"
    if "GARIB RATH" in name:
        return "garib_rath"
    if "HERITAGE" in name:
        return "heritage"
    if "MEMU" in name:
        return "demu"
    if " MEM" in name:
        return "demu"
    if "DEMU" in name:
        return "demu"

    if 30000 <= n <= 39999:
        return "suburban"
    if 40000 <= n <= 49999:
        return "suburban"
    if 90000 <= n <= 99999:
        return "suburban"
    if 60000 <= n <= 69999:
        return "demu"
    if 70000 <= n <= 79999:
        return "demu"
    if 50000 <= n <= 59999:
        return "passenger"
    if 12000 <= n <= 12999:
        return "superfast"
    if 20000 <= n <= 29999:
        return "express"
    if 10000 <= n <= 19999:
        return "express"
    if 1000 <= n <= 9999:
        return "special"

    return "unknown"


def derive_runs_on_days(
    train_name: str, train_number: int, train_type: str
) -> list[str]:
    name = train_name.upper()
    n = int(train_number)

    if "BI-W" in name or "BI W" in name or "BIWEEKLY" in name or "BI-WEEKLY" in name:
        return ["mon", "thu"]

    if name.endswith(" WE") or " -WE" in name or "- WE" in name or "WEEKLY" in name:
        return ["tue"]

    if (
        "TRI-W" in name
        or "TRI W" in name
        or "TRIWEEKLY" in name
        or "TRI-WEEKLY" in name
    ):
        return ["mon", "wed", "fri"]

    if (
        name.endswith(" SPL")
        or name.endswith(" SP")
        or " SPL " in name
        or "SPECIAL" in name
    ):
        return []

    if 30000 <= n <= 39999:
        return ALL_DAYS
    if 40000 <= n <= 49999:
        return ALL_DAYS
    if 90000 <= n <= 99999:
        return ALL_DAYS
    if 60000 <= n <= 79999:
        return ALL_DAYS

    if "MEMU" in name or " MEM" in name:
        return ALL_DAYS

    if any(
        k in name
        for k in [
            "RAJDHANI",
            "SHATABDI",
            "DURONTO",
            "VANDE BHARAT",
            "TEJAS",
            "GATIMAAN",
            "HUMSAFAR",
            "ANTYODAYA",
            "GARIB RATH",
            "GARIBRATH",
        ]
    ):
        return ALL_DAYS

    if name.endswith(" SF") or " SF " in name:
        return ALL_DAYS

    if "LINK" in name:
        return ALL_DAYS

    return ALL_DAYS


# ─── Helpers ──────────────────────────────────────────────────────────────────


def parse_time(val: str):
    if not val or str(val).strip() == "00:00:00":
        return None
    return str(val).strip()


def calc_halt_minutes(arrival, departure) -> int:
    if not arrival or not departure:
        return 0
    try:
        fmt = "%H:%M:%S"
        arr = datetime.strptime(arrival, fmt)
        dep = datetime.strptime(departure, fmt)
        diff = (dep - arr).seconds // 60
        if diff < 0:
            diff += 24 * 60
        return diff
    except Exception:
        return 0


def new_id():
    return uuid.uuid4()


def now_utc():
    return get_utc_timezone()


# ─── CSV Loading ──────────────────────────────────────────────────────────────


def load_and_clean_csv(path: Path) -> pd.DataFrame:
    print(f"\n[1/5] Reading CSV: {path}")
    df = pd.read_csv(
        path,
        dtype={"Train No": str, "SEQ": str, "Distance": str},
        low_memory=False,
    )

    total_before = len(df)
    print(f"      Raw rows: {total_before:,}")

    df = df[df["Train No"].str.match(r"^\d+$", na=False)]
    df = df[df["Distance"].str.match(r"^\d+$", na=False)]

    str_cols = df.select_dtypes(include="object").columns
    df[str_cols] = df[str_cols].apply(lambda col: col.str.strip())

    total_after = len(df)
    print(
        f"      Clean rows: {total_after:,}  (removed {total_before - total_after} bad rows)"
    )

    df["Train No"] = df["Train No"].astype(int)
    df["SEQ"] = df["SEQ"].astype(int)
    df["Distance"] = df["Distance"].astype(int)
    return df


# ─── Data Extraction ──────────────────────────────────────────────────────────


def extract_stations(df: pd.DataFrame) -> pd.DataFrame:
    print("\n[2/5] Extracting unique stations...")
    stops = df[["Station Code", "Station Name"]].drop_duplicates()
    stops.columns = ["station_code", "station_name"]
    src = df[["Source Station", "Source Station Name"]].drop_duplicates()
    src.columns = ["station_code", "station_name"]
    dst = df[["Destination Station", "Destination Station Name"]].drop_duplicates()
    dst.columns = ["station_code", "station_name"]
    all_stations = (
        pd.concat([stops, src, dst])
        .drop_duplicates(subset=["station_code"])
        .reset_index(drop=True)
    )
    print(f"      Unique stations: {len(all_stations):,}")
    return all_stations


def extract_trains(df: pd.DataFrame) -> pd.DataFrame:
    print("\n[3/5] Extracting unique trains...")
    trains = (
        df[["Train No", "Train Name", "Source Station", "Destination Station"]]
        .drop_duplicates(subset=["Train No"])
        .reset_index(drop=True)
    )
    trains.columns = [
        "train_number",
        "train_name",
        "source_station_code",
        "destination_station_code",
    ]
    print(f"      Unique trains: {len(trains):,}")
    return trains


def extract_stops(df: pd.DataFrame) -> pd.DataFrame:
    print("\n[4/5] Extracting train stops...")
    stops = df[
        [
            "Train No",
            "SEQ",
            "Station Code",
            "Arrival time",
            "Departure Time",
            "Distance",
        ]
    ].copy()
    stops.columns = [
        "train_number",
        "sequence_number",
        "station_code",
        "arrival_raw",
        "departure_raw",
        "distance_km",
    ]
    print(f"      Total stops: {len(stops):,}")
    return stops


# ─── DB Upsert Functions ──────────────────────────────────────────────────────


async def upsert_stations(session, stations_df) -> dict:
    print("\n      Upserting stations...", end="", flush=True)

    records = []
    for _, row in stations_df.iterrows():
        records.append(
            {
                "id": new_id(),
                "station_code": row["station_code"],
                "station_name": row["station_name"],
                # CSV has no city/state/geo data — seeded as UNKNOWN.
                # Run scripts/enrich_stations.py later to fill from data.gov.in.
                "city": "UNKNOWN",
                "state": "UNKNOWN",
                "zone": None,  # nullable — fine
                "latitude": None,  # nullable — fine
                "longitude": None,  # nullable — fine
                "is_junction": False,
                "is_remote_location": False,
                "is_active": True,
                "created_at": now_utc(),
                "updated_at": now_utc(),
            }
        )

    inserted = 0
    for i in range(0, len(records), BATCH_SIZE):
        batch = records[i : i + BATCH_SIZE]
        stmt = (
            pg_insert(Stations)
            .values(batch)
            .on_conflict_do_nothing(index_elements=["station_code"])
        )
        result = await session.execute(stmt)
        inserted += result.rowcount

    result = await session.execute(select(Stations.station_code, Stations.id))
    station_map = {row.station_code: row.id for row in result.fetchall()}

    skipped = len(records) - inserted
    print(f" {len(records):,} processed ({inserted} new, {skipped} already existed) ✅")
    return station_map


async def upsert_trains(session, trains_df, station_map) -> dict:
    print(
        "      Upserting trains (setting train_type + runs_on_days)...",
        end="",
        flush=True,
    )

    records = []
    skipped = 0

    for _, row in trains_df.iterrows():
        src_id = station_map.get(row["source_station_code"])
        dst_id = station_map.get(row["destination_station_code"])
        if not src_id or not dst_id:
            skipped += 1
            continue

        train_type = derive_train_type(row["train_name"], row["train_number"])
        runs_on_days = derive_runs_on_days(
            row["train_name"],
            row["train_number"],
            train_type,
        )

        records.append(
            {
                "id": new_id(),
                "train_number": str(row["train_number"]),
                "train_name": row["train_name"],
                "train_type": train_type,
                "runs_on_days": runs_on_days,
                "source_station_id": src_id,
                "destination_station_id": dst_id,
                "is_active": True,
                "created_at": now_utc(),
                "updated_at": now_utc(),
            }
        )

    for i in range(0, len(records), BATCH_SIZE):
        batch = records[i : i + BATCH_SIZE]
        stmt = (
            pg_insert(Trains)
            .values(batch)
            .on_conflict_do_update(
                index_elements=["train_number"],
                set_={
                    "train_type": pg_insert(Trains).excluded.train_type,
                    "runs_on_days": pg_insert(Trains).excluded.runs_on_days,
                    "updated_at": pg_insert(Trains).excluded.updated_at,
                },
            )
        )
        await session.execute(stmt)

    result = await session.execute(select(Trains.train_number, Trains.id))
    train_map = {int(row.train_number): row.id for row in result.fetchall()}

    print(f" {len(records):,} processed (skipped {skipped} missing stations) ✅")
    return train_map


async def upsert_stops(session, stops_df, train_map, station_map) -> None:
    print("      Upserting train stops (this takes ~30s)...")

    records = []
    skipped = 0

    for _, row in stops_df.iterrows():
        train_id = train_map.get(row["train_number"])
        station_id = station_map.get(row["station_code"])
        if not train_id or not station_id:
            skipped += 1
            continue

        arrival = parse_time(row["arrival_raw"])
        departure = parse_time(row["departure_raw"])

        records.append(
            {
                "id": new_id(),
                "train_id": train_id,
                "station_id": station_id,
                "sequence_number": int(row["sequence_number"]),
                "arrival_time": arrival,
                "departure_time": departure,
                "distance_km": int(row["distance_km"]),
                "halt_minutes": calc_halt_minutes(arrival, departure),
                "day_number": 1,  # FIX: CSV is single-day; multi-day trains enriched separately
                "is_source": (int(row["sequence_number"]) == 1),
                "is_destination": (departure is None and arrival is not None),
                "is_active": True,
                "created_at": now_utc(),
                "updated_at": now_utc(),
            }
        )

    total = len(records)
    for start in range(0, total, BATCH_SIZE):
        batch = records[start : start + BATCH_SIZE]
        stmt = (
            pg_insert(TrainStations)
            .values(batch)
            .on_conflict_do_nothing(
                index_elements=["train_id", "station_id", "sequence_number"]
            )
        )
        await session.execute(stmt)
        pct = int((start + len(batch)) / total * 100)
        print(
            f"\r      Progress: {pct}%  ({start + len(batch):,}/{total:,})",
            end="",
            flush=True,
        )

    print(
        f"\r      {total:,} stops processed (skipped {skipped} unmapped) ✅          "
    )


# ─── Main ─────────────────────────────────────────────────────────────────────


async def main():
    start_time = time.time()

    print("=" * 60)
    print("  RailMind — Train Data Seeder")
    print("=" * 60)
    print(f"  CSV:        {CSV_PATH}")
    print(f"  Batch size: {BATCH_SIZE}")
    print(f"  Dry run:    {DRY_RUN}")
    print("=" * 60)

    df = load_and_clean_csv(CSV_PATH)
    stations_df = extract_stations(df)
    trains_df = extract_trains(df)
    stops_df = extract_stops(df)

    if DRY_RUN:
        print("\n[DRY RUN] Parsing complete. No data written to DB.")
        print(f"  Would upsert {len(stations_df):,} stations")
        print(f"  Would upsert {len(trains_df):,} trains")
        print(f"  Would upsert {len(stops_df):,} stops")
        print("\n  Sample train type derivations:")
        for _, row in trains_df.head(15).iterrows():
            t = derive_train_type(row["train_name"], row["train_number"])
            d = derive_runs_on_days(
                row["train_name"],
                row["train_number"],
                t,
            )
            print(
                f"    {str(row['train_number']):>6}  {row['train_name']:<35} → {t:<15} {d}"
            )
        return

    print("\n[5/5] Upserting into railmind_db...")

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
                station_map = await upsert_stations(session, stations_df)
                train_map = await upsert_trains(session, trains_df, station_map)
                await upsert_stops(session, stops_df, train_map, station_map)
            except Exception as e:
                print(f"\n[ERROR] {e}")
                raise

    await engine.dispose()

    elapsed = time.time() - start_time
    print(f"\n{'=' * 60}")
    print(f"  Seeding complete in {elapsed:.1f}s")
    print(f"  Stations : {len(stations_df):,}")
    print(f"  Trains   : {len(trains_df):,}")
    print(f"  Stops    : {len(stops_df):,}")
    print(f"{'=' * 60}\n")


if __name__ == "__main__":
    asyncio.run(main())
