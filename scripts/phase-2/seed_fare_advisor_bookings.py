# AI Fare Predictor — demand-curve mock booking seeder (Phase 2, Feature 02).
#
# WHY a separate seeder (vs seed_autofill_bookings.py):
#   Autofill seeds per-USER bookings (~1 booking per journey) — perfect for
#   "what class does this user pick", useless for "will this journey sell out".
#   The Fare Advisor (Book-Now-vs-Wait) needs the opposite shape: per-JOURNEY
#   demand CURVES — many bookings for the same (train, class, quota, date),
#   spread over lead-time, filling confirmed seats until capacity then
#   waitlisting. That curve is what makes the L2 label (sellout_lead, see
#   planning doc §8.1) and the L1 fill-rate signal learnable.
#
# DESIGN (see docs/ai-fare-predictor-planning.md §8):
#   * A journey = (train, train_class, quota, journey_date).
#   * Each journey gets a demand "load factor" computed ONLY from OBSERVABLE
#     features (train_type, festival month, weekend, distance, class) + i.i.d.
#     noise — NO hidden per-train randomness (avoids the autofill P18 trap where
#     the signal isn't in any column the model can see).
#   * demand_count = round(load * capacity). load>1 -> oversubscribed -> sells
#     out; load<1 -> never sells out (a legit CAN_WAIT journey).
#   * Each booking gets a lead (days before journey) drawn from a recency-skewed
#     curve (+ a Tatkal spike for TQ). Bookings are ordered by lead DESC (time
#     order); first `capacity` are CONFIRMED, the rest WAITLISTED -> the
#     capacity-th booking's lead is the sellout onset; WL leads sit just after.
#   * Future journeys are truncated at `booked_at <= now` -> realistic partial
#     fills "as of today" (lights up the L1 live path + booking velocity).
#   * SeatInventories for each journey is UPDATED to the computed fill
#     (available/wl) so the L1 fill-rate signal is alive too.
#
# Scope notes:
#   * Train-level journey key (no segment) — matches planning doc §8.1 v1.
#   * No BookingPassengers rows: the fare-advisor pipeline never reads them; one
#     Bookings row = one demand event. Keeps the seeder focused.
#   * PNR prefix "D" (demand) so --clean targets only these, leaving autofill's
#     "M" bookings untouched.
#
# Usage:
#   APP_ENV=local ./venv/bin/python scripts/phase-2/seed_fare_advisor_bookings.py            # default run
#   APP_ENV=local ./venv/bin/python scripts/phase-2/seed_fare_advisor_bookings.py --journeys 50   # small
#   APP_ENV=local ./venv/bin/python scripts/phase-2/seed_fare_advisor_bookings.py --clean    # delete D-bookings
#   APP_ENV=local ./venv/bin/python scripts/phase-2/seed_fare_advisor_bookings.py --dry-run  # plan only
import argparse
import asyncio
import sys
import time
import uuid
from collections import Counter
from datetime import date, datetime, time as dtime, timedelta, timezone
from pathlib import Path

parser = argparse.ArgumentParser(
    description="Seed demand-curve mock bookings for the Fare Advisor"
)
parser.add_argument(
    "--journeys", type=int, default=2500, help="number of distinct journeys to seed"
)
parser.add_argument("--seed", type=int, default=42, help="base RNG seed (reproducible)")
parser.add_argument(
    "--clean",
    action="store_true",
    help="delete demand (D-prefix) bookings instead of seeding",
)
parser.add_argument(
    "--force", action="store_true", help="seed even if demand bookings already exist"
)
parser.add_argument(
    "--dry-run", action="store_true", help="print the plan and exit without writing"
)
args = parser.parse_args()

import random

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(_PROJECT_ROOT))

from sqlalchemy import delete, func, select, text
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.db.base import DATABASE_URL, DB_SCHEMA
from app.db.models.booking import Bookings
from app.db.models.train import SeatInventories
from app.db.models.user import Users
from app.utils.helpers import get_utc_timezone

# ── identifiers / scope ───────────────────────────────────────────────────────
MOCK_EMAIL_LIKE = "mock.user%@railmind.test"
PNR_PREFIX = "D"  # demand bookings: D000000001 .. (10 chars total)

# ── date window (relative to today) ───────────────────────────────────────────
PAST_DAYS = 120  # completed journeys -> L2 training curves
FUTURE_DAYS = 30  # upcoming journeys -> live L1 partial fills
PAST_BIAS = 0.75  # fraction of journeys drawn from the past

# ── capacity per class (confirmed seats) ──────────────────────────────────────
CAPACITY = {"SL": 72, "3A": 64, "2A": 46, "1A": 24, "CC": 78, "2S": 108}
CLASS_WEIGHTS = {"SL": 0.34, "3A": 0.30, "2A": 0.12, "CC": 0.12, "2S": 0.08, "1A": 0.04}
WL_MAX = 200

# ── quota mix + lead-curve mean (days) ────────────────────────────────────────
QUOTA_WEIGHTS = {"GN": 0.85, "TQ": 0.15}
LEAD_MEAN = {"GN": 18.0, "TQ": 1.4}  # GN spreads over weeks; TQ opens ~1 day before
MAX_LEAD = 60

# ── demand model — load factor from OBSERVABLE features only ───────────────────
# Higher load also books EARLIER (popular journeys fill up sooner) -> a larger
# sellout_lead. Without this, even oversubscribed journeys sell out only at the
# last day (the marginal booking is always a late arrival), giving no learnable
# spread between "festival train sells out 3 weeks early" and "sells out at 2 days".
BASE_LOAD = 1.00  # median load; mults below push a healthy fraction over 1.0
LEAD_LOAD_BOOST = (
    0.55  # eff_mean = LEAD_MEAN * (1 + LEAD_LOAD_BOOST * max(0, load - 1))
)
TYPE_DEMAND = {
    "RAJDHANI": 1.40,
    "SHATABDI": 1.40,
    "DURONTO": 1.30,
    "GARIB_RATH": 1.20,
    "JAN_SHATABDI": 1.15,
    "SUPERFAST": 1.10,
    "EXPRESS": 1.00,
    "PASSENGER": 0.80,
}
FESTIVAL_MONTHS = {3, 10, 11}
FESTIVAL_MULT = 1.30
WEEKEND_MULT = 1.15

# ── fare model (rough INR; realistic ordering, not exact IRCTC) ────────────────
BASE_FARE = {"2S": 25, "SL": 45, "CC": 90, "3A": 130, "2A": 220, "1A": 420}
PER_KM = {"2S": 0.55, "SL": 0.75, "CC": 1.6, "3A": 1.95, "2A": 2.7, "1A": 4.5}


def compute_fare(train_class: str, dist_km: int) -> float:
    return float(
        round(BASE_FARE.get(train_class, 60) + PER_KM.get(train_class, 1.0) * dist_km)
    )


def now_utc() -> datetime:
    return get_utc_timezone()


def weighted_choice(weights: dict, rng: random.Random) -> str:
    keys = list(weights)
    return rng.choices(keys, weights=[weights[k] for k in keys], k=1)[0]


def load_factor(train_type: str, jd: date, dist: int, rng: random.Random) -> float:
    """Demand relative to capacity, from observable features + i.i.d. noise."""
    type_mult = TYPE_DEMAND.get(train_type, 1.0)
    fest = FESTIVAL_MULT if jd.month in FESTIVAL_MONTHS else 1.0
    wknd = WEEKEND_MULT if jd.weekday() >= 5 else 1.0
    dist_mult = 1.10 if dist > 1000 else (0.95 if dist < 400 else 1.0)
    noise = rng.uniform(0.65, 1.25)
    return BASE_LOAD * type_mult * fest * wknd * dist_mult * noise


def draw_lead(quota: str, load: float, rng: random.Random) -> int:
    """Lead (days before journey) from a recency-skewed curve. Popular journeys
    (load>1) book earlier -> larger mean -> they sell out sooner (bigger
    sellout_lead). TQ always clusters at 0-1 (Tatkal opens ~1 day before)."""
    eff_mean = LEAD_MEAN[quota] * (1 + LEAD_LOAD_BOOST * max(0.0, load - 1.0))
    return min(int(rng.expovariate(1.0 / eff_mean)), MAX_LEAD)


# ── train pool (real trains: id, route, distance, type, departure hour) ───────
async def load_train_pool(session) -> list[dict]:
    sql = text(
        f"""
        SELECT t.id AS train_id, t.source_station_id AS src,
               t.destination_station_id AS dst, t.train_type AS ttype,
               r.dist AS dist
        FROM {DB_SCHEMA}.trains t
        JOIN (
            SELECT train_id, max(distance_km) AS dist
            FROM {DB_SCHEMA}.train_stations GROUP BY train_id
        ) r ON r.train_id = t.id
        WHERE r.dist BETWEEN 50 AND 2500
        """
    )
    rows = (await session.execute(sql)).fetchall()
    return [
        {
            "train_id": r.train_id,
            "src": r.src,
            "dst": r.dst,
            "ttype": r.ttype or "EXPRESS",
            "dist": int(r.dist),
        }
        for r in rows
    ]


async def get_mock_user_ids(session) -> list:
    rows = (
        await session.execute(
            select(Users.id)
            .where(Users.email.like(MOCK_EMAIL_LIKE))
            .order_by(Users.email)
        )
    ).fetchall()
    return [r.id for r in rows]


def pick_journey_date(today: date, rng: random.Random) -> date:
    if rng.random() < PAST_BIAS:
        return today - timedelta(days=rng.randint(1, PAST_DAYS))
    return today + timedelta(days=rng.randint(0, FUTURE_DAYS))


def build_journeys(
    train_pool: list[dict], n: int, today: date, rng: random.Random
) -> list[dict]:
    """Pick n distinct (train, class, quota, date) journeys with a demand profile."""
    seen, journeys = set(), []
    attempts = 0
    while len(journeys) < n and attempts < n * 5:
        attempts += 1
        train = rng.choice(train_pool)
        cls = weighted_choice(CLASS_WEIGHTS, rng)
        quota = weighted_choice(QUOTA_WEIGHTS, rng)
        jd = pick_journey_date(today, rng)
        key = (train["train_id"], cls, quota, jd)
        if key in seen:
            continue
        seen.add(key)
        journeys.append({"train": train, "class": cls, "quota": quota, "jd": jd})
    return journeys


def generate_curve(journey: dict, today: date, rng: random.Random) -> dict:
    """Turn a journey's demand into ordered bookings (lead, status) truncated at
    'today', plus the resulting inventory fill. Returns None if nothing visible."""
    train, cls, quota, jd = (
        journey["train"],
        journey["class"],
        journey["quota"],
        journey["jd"],
    )
    capacity = CAPACITY[cls]
    load = load_factor(train["ttype"], jd, train["dist"], rng)
    demand_count = max(0, round(load * capacity))
    if demand_count == 0:
        return None

    leads = sorted(
        (draw_lead(quota, load, rng) for _ in range(demand_count)), reverse=True
    )
    # assign CONFIRMED to the first `capacity` arrivals (time order = lead DESC)
    bookings = []
    for i, lead in enumerate(leads):
        booked_at = datetime.combine(
            jd - timedelta(days=lead), dtime(10, 0), tzinfo=timezone.utc
        )
        if booked_at > now_utc():  # future journeys: can't book ahead of now
            continue
        status = "CONFIRMED" if i < capacity else "WAITLISTED"
        bookings.append({"lead": lead, "status": status, "booked_at": booked_at})
    if not bookings:
        return None

    confirmed = sum(1 for b in bookings if b["status"] == "CONFIRMED")
    waitlisted = len(bookings) - confirmed
    return {
        "bookings": bookings,
        "capacity": capacity,
        "available": max(0, capacity - confirmed),
        "wl_count": min(waitlisted, WL_MAX),
        "sold_out": waitlisted > 0,
    }


async def upsert_inventories(session, inv_rows: list[dict]) -> None:
    """Create-or-update SeatInventories with the computed fill for each journey."""
    ts = now_utc()
    for i in range(0, len(inv_rows), 1000):
        chunk = inv_rows[i : i + 1000]
        values = [
            {
                "id": uuid.uuid4(),
                "train_id": r["train_id"],
                "journey_date": r["jd"],
                "train_class": r["class"],
                "quota": r["quota"],
                "total_confirmed_seats": r["capacity"],
                "available_confirmed_seats": r["available"],
                "total_rac_berths": 0,
                "total_rac_slots": 0,
                "available_rac_slots": 0,
                "wl_count": r["wl_count"],
                "wl_max": WL_MAX,
                "is_chart_prepared": False,
                "chart_status": "NOT_PREPARED",
                "quota_released_seats": 0,
                "is_active": True,
                "created_at": ts,
                "updated_at": ts,
            }
            for r in chunk
        ]
        stmt = pg_insert(SeatInventories).values(values)
        stmt = stmt.on_conflict_do_update(
            index_elements=["train_id", "journey_date", "train_class", "quota"],
            set_={
                "total_confirmed_seats": stmt.excluded.total_confirmed_seats,
                "available_confirmed_seats": stmt.excluded.available_confirmed_seats,
                "wl_count": stmt.excluded.wl_count,
                "updated_at": stmt.excluded.updated_at,
            },
        )
        await session.execute(stmt)


async def clean(session) -> None:
    res = await session.execute(
        delete(Bookings).where(Bookings.pnr_number.like(f"{PNR_PREFIX}%"))
    )
    await session.commit()
    print(f"\n  Deleted {res.rowcount} demand bookings (D-prefix).")
    print("  (SeatInventories fills left as-is; a re-seed overwrites them.)")


async def main() -> None:
    start = time.time()
    print("=" * 64)
    print("  RailMind — Fare Advisor Demand-Curve Seeder (Phase 2)")
    print("=" * 64)
    if args.clean:
        print("  Mode:     CLEAN")
    else:
        print(f"  Journeys: {args.journeys:,}")
        print(
            f"  Window:   today-{PAST_DAYS}d .. today+{FUTURE_DAYS}d  (past bias {PAST_BIAS})"
        )
        print(f"  RNG seed: {args.seed}")
    print(f"  Schema:   {DB_SCHEMA}")
    print("=" * 64)

    engine = create_async_engine(
        DATABASE_URL,
        echo=False,
        pool_size=5,
        max_overflow=5,
        connect_args={"server_settings": {"search_path": f'"{DB_SCHEMA}"'}},
    )
    async_session = async_sessionmaker(
        bind=engine, class_=AsyncSession, expire_on_commit=False
    )

    if args.clean:
        async with async_session() as session:
            try:
                await clean(session)
            except Exception as e:
                await session.rollback()
                print(f"\n[ERROR] {e}")
                raise
        await engine.dispose()
        print(f"\n  Done in {time.time() - start:.1f}s\n")
        return

    rng = random.Random(args.seed)
    today = date.today()

    async with async_session() as session:
        user_ids = await get_mock_user_ids(session)
        if not user_ids:
            print("\n[ERROR] No mock users found. Run seed_mock_users.py first.")
            await engine.dispose()
            return

        existing = (
            await session.execute(
                select(Bookings.id)
                .where(Bookings.pnr_number.like(f"{PNR_PREFIX}%"))
                .limit(1)
            )
        ).first()
        if existing and not args.force:
            print(
                "\n[ABORT] Demand bookings already exist. Run with --clean first (or --force)."
            )
            await engine.dispose()
            return

        print("\n  Loading real train pool…")
        train_pool = await load_train_pool(session)
        print(f"    {len(train_pool):,} trains (distance 50-2500 km)")
        if not train_pool:
            print("\n[ERROR] No trains found. Seed trains first.")
            await engine.dispose()
            return

        journeys = build_journeys(train_pool, args.journeys, today, rng)
        print(f"    {len(journeys):,} distinct journeys planned")

        if args.dry_run:
            # quick demand preview without writing
            sold = sum(
                1
                for j in journeys
                if (
                    load_factor(
                        j["train"]["ttype"],
                        j["jd"],
                        j["train"]["dist"],
                        random.Random(0),
                    )
                    > 1.0
                )
            )
            print(
                f"\n[DRY RUN] ~{sold:,} journeys look oversubscribed (load>1, rough). Nothing written."
            )
            await engine.dispose()
            return

        booking_rows, inv_rows = [], []
        pnr = 1
        contested = 0
        sellout_leads: list[int] = []
        for j in journeys:
            curve = generate_curve(j, today, rng)
            if curve is None:
                continue
            train = j["train"]
            fare = compute_fare(j["class"], train["dist"])
            if curve["sold_out"]:
                contested += 1
                wl_leads = [
                    b["lead"] for b in curve["bookings"] if b["status"] == "WAITLISTED"
                ]
                if wl_leads:
                    sellout_leads.append(max(wl_leads))
            for b in curve["bookings"]:
                booking_rows.append(
                    {
                        "id": uuid.uuid4(),
                        "user_id": rng.choice(user_ids),
                        "train_id": train["train_id"],
                        "pnr_number": f"{PNR_PREFIX}{pnr:09d}",
                        "booking_status": b["status"],
                        "journey_date": j["jd"],
                        "source_station_id": train["src"],
                        "destination_station_id": train["dst"],
                        "train_class": j["class"],
                        "quota": j["quota"],
                        "total_fare": fare,
                        "booked_at": b["booked_at"],
                        "is_active": True,
                        "created_at": b["booked_at"],
                        "updated_at": b["booked_at"],
                    }
                )
                pnr += 1
            inv_rows.append(
                {
                    "train_id": train["train_id"],
                    "jd": j["jd"],
                    "class": j["class"],
                    "quota": j["quota"],
                    "capacity": curve["capacity"],
                    "available": curve["available"],
                    "wl_count": curve["wl_count"],
                }
            )

        print(
            f"\n  Writing {len(booking_rows):,} bookings across {len(inv_rows):,} journeys…"
        )
        for i in range(0, len(booking_rows), 2000):
            await session.execute(
                pg_insert(Bookings).values(booking_rows[i : i + 2000])
            )
        await upsert_inventories(session, inv_rows)
        await session.commit()

    await engine.dispose()
    elapsed = time.time() - start
    realized = len(inv_rows)
    cf = 100 * contested / realized if realized else 0
    avg_sl = sum(sellout_leads) / len(sellout_leads) if sellout_leads else 0
    print(f"\n{'=' * 64}")
    print(f"  Done in {elapsed:.1f}s")
    print(f"  Journeys realized : {realized:,}")
    print(f"  Contested (sold out): {contested:,}  ({cf:.1f}%)")
    print(
        f"  Bookings written  : {len(booking_rows):,}  (avg {len(booking_rows)/max(realized,1):.1f}/journey)"
    )
    print(f"  Mean sellout_lead : {avg_sl:.1f} days  (n={len(sellout_leads)})")
    print(f"{'=' * 64}\n")


if __name__ == "__main__":
    asyncio.run(main())
