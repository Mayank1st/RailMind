"""
scripts/seed_fare_rules.py

Seeder — populates fare_rules table with official Indian Railways
fare structure (effective 01.01.2020, revised 31.03.2023 + July 2025).

Usage:
    python scripts/seed_fare_rules.py
    python scripts/seed_fare_rules.py --dry-run
"""

import asyncio
import argparse
import sys
import uuid
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_PROJECT_ROOT))

parser = argparse.ArgumentParser(description="Seed fare rules")
parser.add_argument(
    "--dry-run", action="store_true", help="Print only — do not write to DB"
)
args = parser.parse_args()

from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.db.base import DATABASE_URL, DB_SCHEMA
from app.db.models.booking import FareRules
from app.utils.helpers import get_utc_timezone


# ─── Fare Rules Data ──────────────────────────────────────────────────────────
# Source: Indian Railways IRCA fare table (01.01.2020, revised July 2025)
#
# base_fare_per_km      — INR per km before telescopic rebate
# minimum_fare          — floor fare in INR (base fare never goes below this)
# reservation_charge    — flat fee in INR (0 for 2S/unreserved)
# superfast_min_charge  — minimum superfast surcharge in INR
# tatkal_multiplier     — base_fare × this = tatkal fare
# gst_percent           — 5% on AC classes, 0% on non-AC

FARE_RULES = [
    {
        "train_class": "2S",
        "base_fare_per_km": 0.30,
        "minimum_fare": 10,
        "reservation_charge": 0,
        "superfast_min_charge": 15,
        "tatkal_multiplier": 1.1,
        "premium_tatkal_min_multiplier": 1.0,
        "premium_tatkal_max_multiplier": 2.0,
        "gst_percent": 0.0,
    },
    {
        "train_class": "SL",
        "base_fare_per_km": 0.50,
        "minimum_fare": 35,
        "reservation_charge": 15,
        "superfast_min_charge": 30,
        "tatkal_multiplier": 1.3,
        "premium_tatkal_min_multiplier": 1.0,
        "premium_tatkal_max_multiplier": 3.0,
        "gst_percent": 0.0,
    },
    {
        "train_class": "3A",
        "base_fare_per_km": 1.25,
        "minimum_fare": 105,
        "reservation_charge": 30,
        "superfast_min_charge": 45,
        "tatkal_multiplier": 1.4,
        "premium_tatkal_min_multiplier": 1.0,
        "premium_tatkal_max_multiplier": 3.0,
        "gst_percent": 5.0,
    },
    {
        "train_class": "3E",
        "base_fare_per_km": 1.10,
        "minimum_fare": 95,
        "reservation_charge": 30,
        "superfast_min_charge": 45,
        "tatkal_multiplier": 1.4,
        "premium_tatkal_min_multiplier": 1.0,
        "premium_tatkal_max_multiplier": 3.0,
        "gst_percent": 5.0,
    },
    {
        "train_class": "2A",
        "base_fare_per_km": 1.80,
        "minimum_fare": 180,
        "reservation_charge": 45,
        "superfast_min_charge": 45,
        "tatkal_multiplier": 1.5,
        "premium_tatkal_min_multiplier": 1.0,
        "premium_tatkal_max_multiplier": 3.0,
        "gst_percent": 5.0,
    },
    {
        "train_class": "1A",
        "base_fare_per_km": 3.50,
        "minimum_fare": 360,
        "reservation_charge": 60,
        "superfast_min_charge": 75,
        "tatkal_multiplier": 1.3,
        "premium_tatkal_min_multiplier": 1.0,
        "premium_tatkal_max_multiplier": 3.0,
        "gst_percent": 5.0,
    },
    {
        "train_class": "CC",
        "base_fare_per_km": 1.20,
        "minimum_fare": 100,
        "reservation_charge": 40,
        "superfast_min_charge": 45,
        "tatkal_multiplier": 1.4,
        "premium_tatkal_min_multiplier": 1.0,
        "premium_tatkal_max_multiplier": 3.0,
        "gst_percent": 5.0,
    },
    {
        "train_class": "FC",
        "base_fare_per_km": 2.50,
        "minimum_fare": 230,
        "reservation_charge": 50,
        "superfast_min_charge": 45,
        "tatkal_multiplier": 1.3,
        "premium_tatkal_min_multiplier": 1.0,
        "premium_tatkal_max_multiplier": 3.0,
        "gst_percent": 0.0,
    },
]


# ─── Main ─────────────────────────────────────────────────────────────────────


async def main() -> None:
    print("=" * 50)
    print("  RailMind — Fare Rules Seeder")
    print("=" * 50)

    if args.dry_run:
        print("\n[DRY RUN] Rules that would be seeded:\n")
        print(
            f"  {'Class':<6} {'Per km':>8} {'Min fare':>10} {'Res fee':>8} {'SF min':>8} {'Tatkal':>8} {'GST':>6}"
        )
        print(f"  {'-'*6} {'-'*8} {'-'*10} {'-'*8} {'-'*8} {'-'*8} {'-'*6}")
        for r in FARE_RULES:
            print(
                f"  {r['train_class']:<6} "
                f"₹{r['base_fare_per_km']:>6.2f} "
                f"₹{r['minimum_fare']:>8} "
                f"₹{r['reservation_charge']:>6} "
                f"₹{r['superfast_min_charge']:>6} "
                f"×{r['tatkal_multiplier']:>6.1f} "
                f"{r['gst_percent']:>5.0f}%"
            )
        print(f"\n  Total: {len(FARE_RULES)} rules")
        return

    now = get_utc_timezone()

    records = [
        {
            "id": uuid.uuid4(),
            "is_active": True,
            "created_at": now,
            "updated_at": now,
            **rule,
        }
        for rule in FARE_RULES
    ]

    engine = create_async_engine(
        DATABASE_URL,
        echo=False,
        pool_size=3,
        connect_args={"server_settings": {"search_path": f'"{DB_SCHEMA}"'}},
    )
    async_session = async_sessionmaker(
        bind=engine, class_=AsyncSession, expire_on_commit=False
    )

    async with async_session() as session:
        async with session.begin():
            stmt = (
                pg_insert(FareRules)
                .values(records)
                .on_conflict_do_update(
                    index_elements=["train_class"],
                    set_={
                        # Update all fare values on re-run — keeps data fresh
                        "base_fare_per_km": pg_insert(
                            FareRules
                        ).excluded.base_fare_per_km,
                        "minimum_fare": pg_insert(FareRules).excluded.minimum_fare,
                        "reservation_charge": pg_insert(
                            FareRules
                        ).excluded.reservation_charge,
                        "superfast_min_charge": pg_insert(
                            FareRules
                        ).excluded.superfast_min_charge,
                        "tatkal_multiplier": pg_insert(
                            FareRules
                        ).excluded.tatkal_multiplier,
                        "premium_tatkal_min_multiplier": pg_insert(
                            FareRules
                        ).excluded.premium_tatkal_min_multiplier,
                        "premium_tatkal_max_multiplier": pg_insert(
                            FareRules
                        ).excluded.premium_tatkal_max_multiplier,
                        "gst_percent": pg_insert(FareRules).excluded.gst_percent,
                        "updated_at": pg_insert(FareRules).excluded.updated_at,
                    },
                )
            )
            await session.execute(stmt)

    await engine.dispose()

    print(f"\n  ✅ {len(records)} fare rules seeded successfully")
    print("=" * 50)


if __name__ == "__main__":
    asyncio.run(main())
