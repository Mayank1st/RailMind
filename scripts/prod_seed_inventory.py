"""
One-off / repeatable PROD seat-inventory seeder + pruner.

Connects to whatever PROD_DATABASE_URL points at (pass the SSH-tunnelled prod
URL), generates a rolling [today, today+DAYS] inventory window ONLY for trains
that already have coaches, and prunes journey_dates older than RETENTION days
that no booking/waitlist references. Idempotent: ON CONFLICT DO NOTHING.

Reuses the exact same constants as the app service so prod matches app logic.

Usage:
    export PROD_DATABASE_URL="postgresql+asyncpg://user:pass@localhost:5433/railmind_db"
    python scripts/prod_seed_inventory.py --days 60 --retention 7
    python scripts/prod_seed_inventory.py --days 60 --dry-run
"""

import argparse
import asyncio
import os
import sys
import uuid
from datetime import date, timedelta
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_PROJECT_ROOT))

from sqlalchemy import text
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.db.base import DB_SCHEMA
from app.db.models.train import SeatInventories
from app.domain.train.constants.seat_inventory import (
    QUOTA_ALLOCATION,
    RAC_BERTHS_PER_COACH,
    SEAT_CONFIG,
    WL_MAX,
)
from app.utils.helpers import get_utc_timezone

parser = argparse.ArgumentParser()
parser.add_argument("--days", type=int, default=60)
parser.add_argument("--retention", type=int, default=7)
parser.add_argument("--dry-run", action="store_true")
args = parser.parse_args()

FLUSH_THRESHOLD = 50_000
BATCH_SIZE = 1_000  # 18 cols/row -> 18k params, under Postgres' 32767 limit


def calc_quota_seats(confirmed_seats: int, percent: int) -> int:
    if percent == 0:
        return 0
    return max(1, int(confirmed_seats * percent / 100))


async def flush(session, records) -> int:
    inserted = 0
    for i in range(0, len(records), BATCH_SIZE):
        stmt = (
            pg_insert(SeatInventories)
            .values(records[i : i + BATCH_SIZE])
            .on_conflict_do_nothing(
                index_elements=["train_id", "journey_date", "train_class", "quota"]
            )
        )
        result = await session.execute(stmt)
        inserted += result.rowcount
    records.clear()
    await session.commit()
    return inserted


async def main() -> None:
    url = os.environ["PROD_DATABASE_URL"]
    engine = create_async_engine(
        url,
        echo=False,
        pool_size=3,
        connect_args={"server_settings": {"search_path": f'"{DB_SCHEMA}"'}},
    )
    async_session = async_sessionmaker(
        bind=engine, class_=AsyncSession, expire_on_commit=False
    )

    today = date.today()
    window = [today + timedelta(days=d) for d in range(args.days + 1)]
    cutoff = today - timedelta(days=args.retention)

    async with async_session() as session:
        dbname = (await session.execute(text("SELECT current_database()"))).scalar()
        print(f"  Connected to DB: {dbname}")
        print(f"  Window: {window[0]} -> {window[-1]} ({len(window)} days)")
        print(f"  Prune cutoff: journey_date < {cutoff}")

        coach_rows = (
            await session.execute(
                text(
                    "SELECT train_id, train_class, count(*) AS c "
                    f"FROM {DB_SCHEMA}.coaches WHERE is_active = true "
                    "GROUP BY train_id, train_class"
                )
            )
        ).all()
        trains = {r.train_id for r in coach_rows}
        print(f"  Coach groups: {len(coach_rows):,} across {len(trains):,} trains")

        projected = 0
        for _, train_class, c in coach_rows:
            if train_class not in SEAT_CONFIG:
                continue
            qa = QUOTA_ALLOCATION.get(train_class, QUOTA_ALLOCATION["SL"])
            confirmed = SEAT_CONFIG[train_class]["confirmed_seats"] * c
            nz = sum(1 for _, p in qa.items() if calc_quota_seats(confirmed, p) > 0)
            projected += nz * len(window)
        print(f"  Projected inventory rows (max, pre-dedupe): {projected:,}")

        if args.dry_run:
            print("\n  [DRY RUN] nothing written.")
            await engine.dispose()
            return

        records = []
        total_inserted = 0
        for train_id, train_class, coach_count in coach_rows:
            if train_class not in SEAT_CONFIG:
                continue
            confirmed_seats = SEAT_CONFIG[train_class]["confirmed_seats"] * coach_count
            rac_berths = RAC_BERTHS_PER_COACH.get(train_class, 0) * coach_count
            rac_slots = rac_berths * 2
            quota_alloc = QUOTA_ALLOCATION.get(train_class, QUOTA_ALLOCATION["SL"])

            for journey_date in window:
                for quota, percent in quota_alloc.items():
                    quota_seats = calc_quota_seats(confirmed_seats, percent)
                    if quota_seats == 0:
                        continue
                    inv_rac_berths = rac_berths if quota == "GN" else 0
                    inv_rac_slots = rac_slots if quota == "GN" else 0
                    records.append(
                        {
                            "id": uuid.uuid4(),
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
                            "created_at": get_utc_timezone(),
                            "updated_at": get_utc_timezone(),
                        }
                    )
            if len(records) >= FLUSH_THRESHOLD:
                total_inserted += await flush(session, records)
                print(f"  Inserted: {total_inserted:,}", flush=True)

        if records:
            total_inserted += await flush(session, records)
        print(f"  Inserted: {total_inserted:,} new inventory rows [done]")

        prune_sql = text(
            f"""
            DELETE FROM {DB_SCHEMA}.seat_inventories si
            WHERE si.journey_date < :cutoff
              AND NOT EXISTS (
                SELECT 1 FROM {DB_SCHEMA}.booking_passengers bp
                WHERE bp.seat_inventory_id = si.id)
              AND NOT EXISTS (
                SELECT 1 FROM {DB_SCHEMA}.waitlists w
                WHERE w.seat_inventory_id = si.id)
            """
        )
        result = await session.execute(prune_sql, {"cutoff": cutoff})
        await session.commit()
        print(f"  Pruned: {result.rowcount} old unreferenced rows")

    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
