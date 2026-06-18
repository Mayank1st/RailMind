"""
scripts/seed_station_clusters.py

Seeder — populates station_clusters + station_cluster_members with the top
metro clusters used by the "nearby stations" search toggle.

Robust + idempotent:
  - only station codes that actually exist in `stations` are linked (missing
    ones are reported and skipped)
  - a cluster whose PRIMARY station is missing is skipped entirely
  - re-running updates cluster metadata and adds any newly-present members

Usage:
    python scripts/seed_station_clusters.py
    python scripts/seed_station_clusters.py --dry-run
    APP_ENV=prod python scripts/seed_station_clusters.py     # seed the VM DB (tunnel)
"""

import argparse
import asyncio
import sys
import uuid
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_PROJECT_ROOT))

parser = argparse.ArgumentParser(description="Seed station clusters")
parser.add_argument(
    "--dry-run", action="store_true", help="Print only — do not write to DB"
)
args = parser.parse_args()

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.db.base import DATABASE_URL, DB_SCHEMA
from app.db.models.station_clusters import StationClusterMembers, StationClusters
from app.db.models.train import Stations
from app.utils.helpers import get_utc_timezone

# ─── Cluster data ─────────────────────────────────────────────────────────────
# (cluster_code, cluster_name, primary_code, [member_codes])
# Member codes that don't exist in `stations` are skipped at seed time.

CLUSTERS = [
    (
        "MUMBAI",
        "Mumbai Metropolitan",
        "BCT",
        ["BCT", "CSTM", "CSMT", "CST", "LTT", "BVI", "DR", "KYN", "PNVL"],
    ),
    ("DELHI", "Delhi NCR", "NDLS", ["NDLS", "DLI", "NZM", "ANVT", "DEE", "GZB"]),
    ("BANGALORE", "Bengaluru", "SBC", ["SBC", "YPR", "BNCE", "BNC"]),
    ("CHENNAI", "Chennai", "MAS", ["MAS", "MSB", "TBM"]),
    ("KOLKATA", "Kolkata", "HWH", ["HWH", "SDAH", "KOAA", "SHM"]),
    ("HYDERABAD", "Hyderabad", "SC", ["SC", "HYB", "KCG"]),
    ("PUNE", "Pune", "PUNE", ["PUNE", "SVJR"]),
    ("AHMEDABAD", "Ahmedabad", "ADI", ["ADI", "MAN"]),
    ("JAIPUR", "Jaipur", "JP", ["JP", "GADJ"]),
    ("LUCKNOW", "Lucknow", "LKO", ["LKO", "LJN"]),
]


async def main() -> None:
    print("=" * 56)
    print("  RailMind — Station Clusters Seeder")
    print("=" * 56)

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
        # Resolve every referenced code → id in one query.
        all_codes = {c for _, _, _, members in CLUSTERS for c in members}
        rows = (
            await session.execute(
                select(Stations.station_code, Stations.id).where(
                    Stations.station_code.in_(all_codes)
                )
            )
        ).all()
        code_to_id = {r.station_code: r.id for r in rows}

        now = get_utc_timezone()
        seeded, skipped_clusters = 0, []

        for cluster_code, cluster_name, primary_code, members in CLUSTERS:
            present = [c for c in members if c in code_to_id]
            missing = [c for c in members if c not in code_to_id]

            if primary_code not in code_to_id:
                skipped_clusters.append(
                    (cluster_code, f"primary {primary_code} missing")
                )
                print(
                    f"  ✗ {cluster_code:<10} SKIPPED — primary {primary_code} not in DB"
                )
                continue

            print(
                f"  • {cluster_code:<10} primary={primary_code}  "
                f"members={present}" + (f"  (missing: {missing})" if missing else "")
            )

            if args.dry_run:
                seeded += 1
                continue

            # One ongoing transaction for the whole run (the resolve SELECT above
            # already opened it); commit once at the end.
            cluster_id = (
                await session.execute(
                    pg_insert(StationClusters)
                    .values(
                        id=uuid.uuid4(),
                        is_active=True,
                        created_at=now,
                        updated_at=now,
                        cluster_code=cluster_code,
                        cluster_name=cluster_name,
                        primary_station_id=code_to_id[primary_code],
                    )
                    .on_conflict_do_update(
                        index_elements=["cluster_code"],
                        set_={
                            "cluster_name": cluster_name,
                            "primary_station_id": code_to_id[primary_code],
                            "updated_at": now,
                        },
                    )
                    .returning(StationClusters.id)
                )
            ).scalar_one()

            member_rows = [
                {
                    "id": uuid.uuid4(),
                    "is_active": True,
                    "created_at": now,
                    "updated_at": now,
                    "cluster_id": cluster_id,
                    "station_id": code_to_id[code],
                }
                for code in present
            ]
            if member_rows:
                await session.execute(
                    pg_insert(StationClusterMembers)
                    .values(member_rows)
                    .on_conflict_do_nothing(constraint="uq_cluster_station")
                )
            seeded += 1

        if not args.dry_run:
            await session.commit()

    await engine.dispose()

    print("-" * 56)
    print(f"  {'[DRY RUN] ' if args.dry_run else ''}clusters processed: {seeded}")
    if skipped_clusters:
        print(f"  skipped: {skipped_clusters}")
    print("=" * 56)


if __name__ == "__main__":
    asyncio.run(main())
