# Smart Form Autofill — persona-driven mock booking seeder (Phase 2).
#
# Seeds 20 mock users x 1000 bookings each with realistic, persona-driven
# patterns (a clear dominant tendency + per-persona noise) so Level-1 (rules)
# and Level-2 (ML) autofill can be trained/tested on data that has *real but
# imperfect* patterns. See the spec in the chat / RailMind docs.
#
# Usage:
#   APP_ENV=local ./venv/bin/python scripts/phase-2/seed_autofill_bookings.py             # seed 20x1000
#   APP_ENV=local ./venv/bin/python scripts/phase-2/seed_autofill_bookings.py --bookings 100   # smaller run
#   APP_ENV=local ./venv/bin/python scripts/phase-2/seed_autofill_bookings.py --clean     # delete mock bookings/passengers
#   APP_ENV=local ./venv/bin/python scripts/phase-2/seed_autofill_bookings.py --dry-run   # show plan, touch nothing
#
# Notes / decisions:
#   * Personas map onto the existing mock.user01..20 (created by seed_mock_users.py).
#   * Each booking is anchored to a REAL train (picked from a distance-bucketed
#     pool) so train_id / source / destination / distance are all valid + realistic.
#   * Journey distance lives in train_stations (not on the booking); we use the
#     train's real route distance and bucket trains into short/medium/long.
#   * Ground truth (intended vs actual class, persona, noise flag, every feature,
#     train/test split) is written to a sidecar CSV — bookings has no metadata col.
#   * journey_date is spread over the PAST 365 days (historical, completed bookings).
import argparse
import asyncio
import csv
import sys
import time
import uuid
from datetime import date, datetime, time as dtime, timedelta, timezone
from pathlib import Path

parser = argparse.ArgumentParser(
    description="Seed persona-driven autofill mock bookings"
)
parser.add_argument(
    "--users", type=int, default=20, help="number of personas/users (max 20)"
)
parser.add_argument("--bookings", type=int, default=1000, help="bookings per user")
parser.add_argument("--seed", type=int, default=42, help="base RNG seed (reproducible)")
parser.add_argument(
    "--test-frac",
    type=float,
    default=0.2,
    help="fraction of each user's bookings tagged 'test'",
)
parser.add_argument(
    "--clean",
    action="store_true",
    help="delete all mock bookings/passengers instead of seeding",
)
parser.add_argument(
    "--force", action="store_true", help="seed even if mock bookings already exist"
)
parser.add_argument(
    "--dry-run", action="store_true", help="print the plan and exit without writing"
)
args = parser.parse_args()

import random

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(_PROJECT_ROOT))

from sqlalchemy import delete, select, text, tuple_
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.db.base import DATABASE_URL, DB_SCHEMA
from app.db.models.booking import BookingPassengers, Bookings
from app.db.models.passengers import Passengers
from app.db.models.train import SeatInventories
from app.db.models.user import Users
from app.utils.helpers import get_utc_timezone

# ── identifiers / scope ───────────────────────────────────────────────────────
MOCK_EMAIL_LIKE = "mock.user%@railmind.test"
PNR_PREFIX = "M"  # mock bookings: M000000001 .. (10 chars total)
CSV_PATH = Path(__file__).resolve().parent / "autofill_ground_truth.csv"

# ── distance buckets (km) ─────────────────────────────────────────────────────
BUCKETS = {"short": (50, 400), "medium": (400, 1000), "long": (1000, 2500)}

# ── fare model (rough INR; realistic ordering, not exact IRCTC) ────────────────
BASE_FARE = {
    "2S": 25,
    "SL": 45,
    "CC": 90,
    "3A": 130,
    "2A": 220,
    "1A": 420,
    "FC": 320,
    "3E": 110,
}
PER_KM = {
    "2S": 0.55,
    "SL": 0.75,
    "CC": 1.6,
    "3A": 1.95,
    "2A": 2.7,
    "1A": 4.5,
    "FC": 3.2,
    "3E": 1.7,
}


def compute_fare(train_class: str, dist_km: int) -> float:
    base = BASE_FARE.get(train_class, 60)
    rate = PER_KM.get(train_class, 1.0)
    return float(round(base + rate * dist_km))


# ── persona config ────────────────────────────────────────────────────────────
# dist = bucket-weights; berth = default berth pref; daypart = required time band;
# fixed_route = reuse one train for every booking; pax = (n_adult,n_child,n_senior)
# distribution is decided in choose_pax(); season = allowed journey months.
PERSONAS = [
    {
        "id": 1,
        "name": "Budget Solo Backpacker",
        "noise": 0.15,
        "dist": {"short": 0.30, "medium": 0.35, "long": 0.35},
        "berth": "NP",
        "quota": "GN",
        "lead": "advance",
    },
    {
        "id": 2,
        "name": "Sleeper Loyalist",
        "noise": 0.20,
        "dist": {"short": 0.30, "medium": 0.40, "long": 0.30},
        "berth": "LB",
        "quota": "GN",
        "lead": "advance",
    },
    {
        "id": 3,
        "name": "Student Commuter",
        "noise": 0.10,
        "dist": {"short": 1.0},
        "berth": "NP",
        "quota": "GN",
        "lead": "normal",
        "daypart": "day",
        "fixed_route": True,
    },
    {
        "id": 4,
        "name": "AC-Only Professional",
        "noise": 0.15,
        "dist": {"short": 0.20, "medium": 0.40, "long": 0.40},
        "berth": "LB",
        "quota": "GN",
        "lead": "advance",
    },
    {
        "id": 5,
        "name": "Premium Executive",
        "noise": 0.15,
        "dist": {"short": 0.10, "medium": 0.50, "long": 0.40},
        "berth": "LB",
        "quota": "GN",
        "lead": "advance",
    },
    {
        "id": 6,
        "name": "Comfort-Conditional",
        "noise": 0.10,
        "dist": {"short": 0.40, "medium": 0.40, "long": 0.20},
        "berth": "LB",
        "quota": "GN",
        "lead": "advance",
    },
    {
        "id": 7,
        "name": "Family Vacationer",
        "noise": 0.20,
        "dist": {"short": 0.10, "medium": 0.40, "long": 0.50},
        "berth": "LB",
        "quota": "GN",
        "lead": "advance",
        "season_boost": {5, 6, 10, 11},
    },
    {
        "id": 8,
        "name": "Large Joint Family",
        "noise": 0.25,
        "dist": {"medium": 0.40, "long": 0.60},
        "berth": "NP",
        "quota": "GN",
        "lead": "advance",
        "season_boost": {10, 11},
    },
    {
        "id": 9,
        "name": "Couple Traveller",
        "noise": 0.15,
        "dist": {"short": 0.30, "medium": 0.40, "long": 0.30},
        "berth": "SL",
        "quota": "GN",
        "lead": "advance",
    },
    {
        "id": 10,
        "name": "Senior Citizen",
        "noise": 0.10,
        "dist": {"short": 0.30, "medium": 0.40, "long": 0.30},
        "berth": "LB",
        "quota": "GN",
        "lead": "advance",
        "daypart": "day",
    },
    {
        "id": 11,
        "name": "Weekly Business Commuter",
        "noise": 0.10,
        "dist": {"short": 0.60, "medium": 0.40},
        "berth": "NP",
        "quota": "GN",
        "lead": "weekly",
        "fixed_route": True,
        "weekday": True,
    },
    {
        "id": 12,
        "name": "Tatkal Last-Minuter",
        "noise": 0.20,
        "dist": {"short": 0.30, "medium": 0.40, "long": 0.30},
        "berth": "NP",
        "quota": "TQ",
        "lead": "tatkal",
    },
    {
        "id": 13,
        "name": "Overnight Long-Hauler",
        "noise": 0.15,
        "dist": {"medium": 0.20, "long": 0.80},
        "berth": "SL",
        "quota": "GN",
        "lead": "advance",
        "daypart": "night",
    },
    {
        "id": 14,
        "name": "Day-Tripper",
        "noise": 0.10,
        "dist": {"short": 1.0},
        "berth": "NP",
        "quota": "GN",
        "lead": "normal",
        "daypart": "day",
    },
    {
        "id": 15,
        "name": "Festival-Only Traveller",
        "noise": 0.25,
        "dist": {"long": 1.0},
        "berth": "NP",
        "quota": "GN",
        "lead": "advance",
        "season": {10, 11, 3},
    },
    {
        "id": 16,
        "name": "Summer-AC Family",
        "noise": 0.20,
        "dist": {"medium": 0.40, "long": 0.60},
        "berth": "MB",
        "quota": "GN",
        "lead": "advance",
        "season": {5, 6},
    },
    {
        "id": 17,
        "name": "Erratic Switcher",
        "noise": 0.45,
        "dist": {"short": 0.33, "medium": 0.34, "long": 0.33},
        "berth": "NP",
        "quota": "GN",
        "lead": "mixed",
    },
    {
        "id": 18,
        "name": "Recency Shifter",
        "noise": 0.15,
        "dist": {"short": 0.20, "medium": 0.40, "long": 0.40},
        "berth": "LB",
        "quota": "GN",
        "lead": "advance",
    },
    {
        "id": 19,
        "name": "Ladies-Quota Solo",
        "noise": 0.15,
        "dist": {"short": 0.20, "medium": 0.50, "long": 0.30},
        "berth": "LB",
        "quota": "LD",
        "lead": "advance",
        "gender": "FEMALE",
    },
    {
        "id": 20,
        "name": "Availability Pragmatist",
        "noise": 0.30,
        "dist": {"short": 0.30, "medium": 0.40, "long": 0.30},
        "berth": "NP",
        "quota": "GN",
        "lead": "normal",
    },
]


def bucket_of(dist_km: int) -> str:
    if dist_km < 400:
        return "short"
    if dist_km <= 1000:
        return "medium"
    return "long"


def choose_bucket(persona, rng) -> str:
    weights = persona["dist"]
    keys = list(weights.keys())
    return rng.choices(keys, weights=[weights[k] for k in keys], k=1)[0]


# ── class logic: returns (intended_class, actual_class) ───────────────────────
def choose_class(persona, bucket, dist_km, i, n, rng):
    pid = persona["id"]
    noise = persona["noise"]
    roll = rng.random()
    noisy = roll < noise

    if pid == 1:  # 2S short, SL medium/long (SL even on long)
        intended = "2S" if bucket == "short" else "SL"
        actual = ("SL" if bucket == "short" else "3A") if noisy else intended
    elif pid == 2:  # SL everywhere; ~20% of >1500km -> 3A
        intended = "SL"
        if dist_km > 1500 and roll < 0.20:
            actual = "3A"
        elif noisy:
            actual = "2S" if bucket == "short" else "3A"
        else:
            actual = "SL"
    elif pid == 3:  # 2S/SL short fixed route
        intended = "2S"
        actual = "SL" if noisy else "2S"
    elif pid == 4:  # 3A always; 2A on >1500km
        intended = "2A" if dist_km > 1500 else "3A"
        if noisy:
            actual = (
                "SL" if rng.random() < 0.25 else ("2A" if intended == "3A" else "3A")
            )
        else:
            actual = intended
    elif pid == 5:  # 2A medium, 1A long; never below 2A
        intended = "1A" if bucket == "long" else "2A"
        actual = ("2A" if intended == "1A" else "1A") if noisy else intended
    elif pid == 6:  # clean distance rule
        if dist_km < 400:
            intended = "CC" if rng.random() < 0.5 else "2S"
        elif dist_km <= 1200:
            intended = "3A"
        else:
            intended = "2A"
        nbr = {"2S": "CC", "CC": "3A", "3A": "2A", "2A": "3A"}
        actual = nbr.get(intended, "3A") if noisy else intended
    elif pid == 7:  # 3A family
        intended = "3A"
        actual = ("SL" if rng.random() < 0.6 else "2A") if noisy else "3A"
    elif pid == 8:  # SL large family
        intended = "SL"
        actual = "3A" if noisy else "SL"
    elif pid == 9:  # 2S short, 3A else
        intended = "2S" if bucket == "short" else "3A"
        actual = ("SL" if intended == "2S" else "2A") if noisy else intended
    elif pid == 10:  # 3A senior + lower berth
        intended = "3A"
        actual = ("2A" if rng.random() < 0.5 else "SL") if noisy else "3A"
    elif pid == 11:  # CC short / 3A medium, fixed route
        intended = "CC" if bucket == "short" else "3A"
        actual = ("2S" if intended == "CC" else "SL") if noisy else intended
    elif pid == 12:  # tatkal 3A/SL erratic
        intended = "3A" if rng.random() < 0.5 else "SL"
        actual = "2S" if noisy else intended
    elif pid == 13:  # overnight SL/3A
        intended = "SL" if rng.random() < 0.5 else "3A"
        actual = "2A" if noisy else intended
    elif pid == 14:  # day 2S/CC
        intended = "2S" if rng.random() < 0.5 else "CC"
        actual = "SL" if noisy else intended
    elif pid == 15:  # festival SL
        intended = "SL"
        actual = "3A" if noisy else "SL"
    elif pid == 16:  # summer 3A family
        intended = "3A"
        actual = ("2A" if rng.random() < 0.5 else "SL") if noisy else "3A"
    elif pid == 17:  # erratic: no real pattern
        intended = "SL" if rng.random() < 0.5 else "3A"
        actual = rng.choice(["SL", "3A", "2S", "2A"]) if noisy else intended
    elif pid == 18:  # recency: first 60% SL, last 40% 3A
        intended = "SL" if i < int(n * 0.6) else "3A"
        actual = ("3A" if intended == "SL" else "SL") if noisy else intended
    elif pid == 19:  # ladies solo 3A
        intended = "3A"
        actual = ("2A" if rng.random() < 0.5 else "SL") if noisy else "3A"
    elif pid == 20:  # availability pragmatist: ~35% flip to whatever's available
        intended = "3A"
        actual = rng.choice(["SL", "2S"]) if rng.random() < 0.35 else "3A"
    else:
        intended = actual = "SL"

    return intended, actual


# ── passenger composition per persona: (n_adult, n_child, n_senior) ───────────
def choose_pax_counts(persona, rng):
    pid = persona["id"]
    if pid in (1, 3, 5, 11, 14, 19):
        return (1, 0, 0)
    if pid in (4, 12, 13, 18, 20):
        return (rng.randint(1, 2), 0, 0)
    if pid == 2:
        return (rng.randint(2, 3), 0, 0)
    if pid == 6:
        return (rng.randint(1, 2), 0, 0)
    if pid == 9:
        return (2, 0, 0)
    if pid == 10:
        return (rng.randint(0, 1), 0, 1)  # senior +/- companion
    if pid in (7, 15):
        return (rng.randint(2, 3), rng.randint(1, 2), rng.randint(0, 1))
    if pid == 8:
        return (2, 2, 2)
    if pid == 16:
        return (2, rng.randint(1, 2), 0)
    if pid == 17:
        return (rng.randint(1, 4), 0, 0)
    return (1, 0, 0)


# ── quota + booking status ────────────────────────────────────────────────────
def choose_quota_status(persona, rng):
    """Returns (quota, booking_status, is_tatkal)."""
    pid = persona["id"]
    if pid == 5:  # sometimes Tatkal
        if rng.random() < 0.20:
            return ("TQ", "CONFIRMED", True)
        return ("GN", "CONFIRMED", False)
    if pid == 8:  # often GNWL (general waitlist)
        return ("GN", "WAITLISTED" if rng.random() < 0.35 else "CONFIRMED", False)
    if pid == 12:  # Tatkal always
        return ("TQ", "CONFIRMED", True)
    if pid == 15:  # GNWL / Tatkal
        r = rng.random()
        if r < 0.40:
            return ("TQ", "CONFIRMED", True)
        if r < 0.70:
            return ("GN", "WAITLISTED", False)
        return ("GN", "CONFIRMED", False)
    if pid == 19:  # Ladies quota often
        return (
            ("LD", "CONFIRMED", False)
            if rng.random() < 0.60
            else ("GN", "CONFIRMED", False)
        )
    return ("GN", "CONFIRMED", False)


def choose_lead_days(persona, is_tatkal, rng):
    if is_tatkal:
        return 1
    mode = persona["lead"]
    if mode == "advance":
        return rng.randint(20, 75)
    if mode == "normal":
        return rng.randint(3, 18)
    if mode == "weekly":
        return rng.randint(2, 3)
    if mode == "tatkal":
        return 1
    return rng.randint(1, 60)  # mixed


# ── journey date pools ────────────────────────────────────────────────────────
def build_date_pool():
    today = date.today()
    all_dates = [today - timedelta(days=d) for d in range(1, 366)]
    by_month = {m: [d for d in all_dates if d.month == m] for m in range(1, 13)}
    weekdays = [d for d in all_dates if d.weekday() < 5]
    return all_dates, by_month, weekdays


def choose_journey_date(persona, date_pool, rng):
    all_dates, by_month, weekdays = date_pool
    if persona.get("season"):
        candidates = [d for m in persona["season"] for d in by_month[m]]
        return rng.choice(candidates)
    if persona.get("weekday"):
        return rng.choice(weekdays)
    if persona.get("season_boost"):
        # 60% of bookings land in the boosted months, else anywhere
        if rng.random() < 0.60:
            candidates = [d for m in persona["season_boost"] for d in by_month[m]]
            return rng.choice(candidates)
    return rng.choice(all_dates)


# ── train pool (real trains bucketed by distance + day/night) ─────────────────
async def load_train_pool(session):
    sql = text(
        f"""
        SELECT t.id AS train_id, t.source_station_id AS src, t.destination_station_id AS dst,
               r.dist AS dist, ts.departure_time AS dep
        FROM {DB_SCHEMA}.trains t
        JOIN (
            SELECT train_id, max(distance_km) AS dist
            FROM {DB_SCHEMA}.train_stations GROUP BY train_id
        ) r ON r.train_id = t.id
        JOIN {DB_SCHEMA}.train_stations ts ON ts.train_id = t.id AND ts.is_source
        WHERE r.dist BETWEEN 50 AND 2500
        """
    )
    rows = (await session.execute(sql)).fetchall()
    pool = {b: {"any": [], "day": [], "night": []} for b in BUCKETS}
    for row in rows:
        dep = row.dep or "12:00:00"
        try:
            hour = int(str(dep)[:2])
        except ValueError:
            hour = 12
        is_day = 6 <= hour < 18
        rec = {
            "train_id": row.train_id,
            "src": row.src,
            "dst": row.dst,
            "dist": int(row.dist),
            "hour": hour,
        }
        b = bucket_of(rec["dist"])
        pool[b]["any"].append(rec)
        pool[b]["day" if is_day else "night"].append(rec)
    return pool


def pick_train(persona, bucket, pool, rng):
    daypart = persona.get("daypart")  # "day" / "night" / None
    band = pool[bucket]
    lst = band.get(daypart) if daypart else None
    if not lst:
        lst = band["any"]
    if not lst:  # bucket empty -> fall back to any non-empty bucket
        for b in ("medium", "short", "long"):
            if pool[b]["any"]:
                lst = pool[b]["any"]
                break
    return rng.choice(lst)


# ── per-user passenger pool ───────────────────────────────────────────────────
def build_passenger_pool(persona, user_idx, rng):
    """Returns list of dicts: full_name, age, gender, is_primary. Indices:
    adults [0,1,7,8], seniors [2,3], children [4,5,6]."""
    if persona.get("gender") == "FEMALE":
        g, o = "FEMALE", "MALE"
    else:
        g, o = ("MALE", "FEMALE") if user_idx % 2 == 0 else ("FEMALE", "MALE")
    return [
        {"full_name": "Self", "age": 34, "gender": g, "is_primary": True},  # 0 adult
        {"full_name": "Spouse", "age": 31, "gender": o, "is_primary": False},  # 1 adult
        {
            "full_name": "Parent",
            "age": 66,
            "gender": g,
            "is_primary": False,
        },  # 2 senior
        {
            "full_name": "In-Law",
            "age": 70,
            "gender": o,
            "is_primary": False,
        },  # 3 senior
        {
            "full_name": "Child One",
            "age": 9,
            "gender": "MALE",
            "is_primary": False,
        },  # 4 child
        {
            "full_name": "Child Two",
            "age": 6,
            "gender": "FEMALE",
            "is_primary": False,
        },  # 5 child
        {
            "full_name": "Child Three",
            "age": 11,
            "gender": "MALE",
            "is_primary": False,
        },  # 6 child
        {"full_name": "Friend", "age": 27, "gender": o, "is_primary": False},  # 7 adult
        {
            "full_name": "Colleague",
            "age": 41,
            "gender": g,
            "is_primary": False,
        },  # 8 adult
    ]


ADULT_IDX = [0, 1, 7, 8]
SENIOR_IDX = [2, 3]
CHILD_IDX = [4, 5, 6]


def select_passenger_indices(n_adult, n_child, n_senior):
    idx = ADULT_IDX[:n_adult] + SENIOR_IDX[:n_senior] + CHILD_IDX[:n_child]
    return idx or [0]


def berth_for(passenger, persona_berth):
    if passenger["age"] >= 60 or passenger["age"] < 12:
        return "LB"  # seniors & children always lower berth
    return persona_berth


# ── seeding ───────────────────────────────────────────────────────────────────
def now_utc():
    return get_utc_timezone()


async def get_mock_users(session, limit):
    rows = (
        await session.execute(
            select(Users.id, Users.email)
            .where(Users.email.like(MOCK_EMAIL_LIKE))
            .order_by(Users.email)
            .limit(limit)
        )
    ).fetchall()
    return rows


async def ensure_inventories(session, combos):
    """Bulk get-or-create seat_inventories for a set of (train_id, jd, class, quota).
    Returns {combo: inventory_id}."""
    if not combos:
        return {}
    combos = list(combos)
    ts = now_utc()
    values = [
        {
            "id": uuid.uuid4(),
            "train_id": tid,
            "journey_date": jd,
            "train_class": cls,
            "quota": q,
            "total_confirmed_seats": 72,
            "available_confirmed_seats": 72,
            "total_rac_berths": 0,
            "total_rac_slots": 0,
            "available_rac_slots": 0,
            "wl_count": 0,
            "wl_max": 200,
            "is_chart_prepared": False,
            "chart_status": "NOT_PREPARED",
            "quota_released_seats": 0,
            "is_active": True,
            "created_at": ts,
            "updated_at": ts,
        }
        for (tid, jd, cls, q) in combos
    ]
    # insert any missing ones (existing rows are left untouched)
    for i in range(0, len(values), 1000):
        stmt = (
            pg_insert(SeatInventories)
            .values(values[i : i + 1000])
            .on_conflict_do_nothing(
                index_elements=["train_id", "journey_date", "train_class", "quota"]
            )
        )
        await session.execute(stmt)
    # read back ids for the exact combos
    id_map = {}
    inv = SeatInventories
    key = tuple_(inv.train_id, inv.journey_date, inv.train_class, inv.quota)
    for i in range(0, len(combos), 1000):
        chunk = combos[i : i + 1000]
        rows = (
            await session.execute(
                select(
                    inv.train_id, inv.journey_date, inv.train_class, inv.quota, inv.id
                ).where(key.in_(chunk))
            )
        ).fetchall()
        for r in rows:
            id_map[(r[0], r[1], r[2], r[3])] = r[4]
    return id_map


async def seed_user(
    session,
    persona,
    user_id,
    user_idx,
    n_bookings,
    base_seed,
    test_frac,
    pnr_start,
    train_pool,
    date_pool,
    csv_rows,
):
    rng = random.Random(base_seed * 1000 + persona["id"])
    persona_berth = persona["berth"]

    # 1. passenger pool for this user
    pool_defs = build_passenger_pool(persona, user_idx, rng)
    pool_ids = []
    pax_rows = []
    for pdef in pool_defs:
        pid = uuid.uuid4()
        pool_ids.append(pid)
        pax_rows.append(
            {
                "id": pid,
                "user_id": user_id,
                "full_name": f"{pdef['full_name']} U{user_idx + 1:02d}",
                "age": pdef["age"],
                "gender": pdef["gender"],
                "berth_preference": persona_berth,
                "is_primary": pdef["is_primary"],
                "is_active": True,
                "created_at": now_utc(),
                "updated_at": now_utc(),
            }
        )
    await session.execute(pg_insert(Passengers).values(pax_rows))

    # 2. fixed-route trains (personas 3, 11) pick one train per bucket up front
    fixed_train = {}
    if persona.get("fixed_route"):
        for b in persona["dist"]:
            fixed_train[b] = pick_train(persona, b, train_pool, rng)

    # 3. generate booking specs
    specs = []
    n_test = int(n_bookings * test_frac)
    for i in range(n_bookings):
        bucket = choose_bucket(persona, rng)
        train = fixed_train.get(bucket) or pick_train(persona, bucket, train_pool, rng)
        dist = train["dist"]
        bucket = bucket_of(dist)  # reconcile with the chosen train's real distance

        intended, actual = choose_class(persona, bucket, dist, i, n_bookings, rng)
        quota, status, is_tatkal = choose_quota_status(persona, rng)
        lead = choose_lead_days(persona, is_tatkal, rng)
        jd = choose_journey_date(persona, date_pool, rng)
        booked_at = datetime.combine(
            jd - timedelta(days=lead), dtime(10, 0), tzinfo=timezone.utc
        )
        time_of_day = "DAY" if 6 <= train["hour"] < 18 else "NIGHT"

        n_ad, n_ch, n_sr = choose_pax_counts(persona, rng)
        pax_idx = select_passenger_indices(n_ad, n_ch, n_sr)
        pax = len(pax_idx)
        per_fare = compute_fare(actual, dist)

        specs.append(
            {
                "id": uuid.uuid4(),
                "train": train,
                "dist": dist,
                "bucket": bucket,
                "intended": intended,
                "actual": actual,
                "quota": quota,
                "status": status,
                "jd": jd,
                "booked_at": booked_at,
                "lead": lead,
                "time_of_day": time_of_day,
                "pax_idx": pax_idx,
                "pax": pax,
                "per_fare": per_fare,
                "split": "test" if i >= (n_bookings - n_test) else "train",
            }
        )

    # 4. resolve seat inventories in bulk
    combos = {(s["train"]["train_id"], s["jd"], s["actual"], s["quota"]) for s in specs}
    inv_map = await ensure_inventories(session, combos)

    # 5. build booking + booking_passenger rows
    booking_rows, bp_rows = [], []
    for n, s in enumerate(specs):
        pnr = f"{PNR_PREFIX}{pnr_start + n:09d}"
        inv_id = inv_map[(s["train"]["train_id"], s["jd"], s["actual"], s["quota"])]
        booking_rows.append(
            {
                "id": s["id"],
                "user_id": user_id,
                "train_id": s["train"]["train_id"],
                "pnr_number": pnr,
                "booking_status": s["status"],
                "journey_date": s["jd"],
                "source_station_id": s["train"]["src"],
                "destination_station_id": s["train"]["dst"],
                "train_class": s["actual"],
                "quota": s["quota"],
                "total_fare": s["per_fare"] * s["pax"],
                "booked_at": s["booked_at"],
                "is_active": True,
                "created_at": s["booked_at"],
                "updated_at": s["booked_at"],
            }
        )
        pstatus = "WL" if s["status"] == "WAITLISTED" else "CNF"
        for pidx in s["pax_idx"]:
            pdef = pool_defs[pidx]
            bp_rows.append(
                {
                    "id": uuid.uuid4(),
                    "booking_id": s["id"],
                    "seat_inventory_id": inv_id,
                    "passenger_id": pool_ids[pidx],
                    "berth_preference": berth_for(pdef, persona_berth),
                    "passenger_status": pstatus,
                    "fare": s["per_fare"],
                    "is_active": True,
                    "created_at": s["booked_at"],
                    "updated_at": s["booked_at"],
                }
            )
        # ground-truth row
        csv_rows.append(
            {
                "pnr": pnr,
                "user_idx": user_idx + 1,
                "persona_id": persona["id"],
                "persona": persona["name"],
                "intended_class": s["intended"],
                "actual_class": s["actual"],
                "is_noise": int(s["intended"] != s["actual"]),
                "distance_km": s["dist"],
                "distance_bucket": s["bucket"],
                "pax": s["pax"],
                "quota": s["quota"],
                "booking_status": s["status"],
                "journey_date": s["jd"].isoformat(),
                "booked_at": s["booked_at"].isoformat(),
                "lead_days": s["lead"],
                "time_of_day": s["time_of_day"],
                "berth_preference": persona_berth,
                "split": s["split"],
            }
        )

    # 6. bulk insert
    for i in range(0, len(booking_rows), 1000):
        await session.execute(pg_insert(Bookings).values(booking_rows[i : i + 1000]))
    for i in range(0, len(bp_rows), 1000):
        await session.execute(
            pg_insert(BookingPassengers).values(bp_rows[i : i + 1000])
        )
    await session.commit()

    noise_n = sum(r["is_noise"] for r in csv_rows[-len(specs) :])
    return len(booking_rows), len(bp_rows), noise_n


async def clean(session):
    user_ids = [r.id for r in await get_mock_users(session, 1000)]
    if not user_ids:
        print("\n  No mock users found — nothing to clean.")
        return
    # booking_passengers cascade from bookings; delete bookings then pool passengers.
    res_b = await session.execute(
        delete(Bookings).where(Bookings.user_id.in_(user_ids))
    )
    res_p = await session.execute(
        delete(Passengers).where(Passengers.user_id.in_(user_ids))
    )
    await session.commit()
    print(
        f"\n  Deleted {res_b.rowcount} bookings (+cascade passengers rows) "
        f"and {res_p.rowcount} master passengers for {len(user_ids)} mock users."
    )
    print(f"  (Seat inventories left intact; sidecar CSV at {CSV_PATH} not removed.)")


async def main():
    start = time.time()
    n_users = min(args.users, 20)
    print("=" * 64)
    print("  RailMind — Smart Autofill Mock Booking Seeder (Phase 2)")
    print("=" * 64)
    if args.clean:
        print("  Mode:          CLEAN")
    else:
        print(f"  Users:         {n_users} personas")
        print(f"  Bookings/user: {args.bookings}  (test fraction {args.test_frac})")
        print(f"  RNG seed:      {args.seed}")
    print(f"  Schema:        {DB_SCHEMA}")
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

    async with async_session() as session:
        users = await get_mock_users(session, n_users)
        if len(users) < n_users:
            print(
                f"\n[ERROR] Found only {len(users)} mock users (need {n_users}). "
                f"Run seed_mock_users.py first."
            )
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
                "\n[ABORT] Mock bookings already exist. Run with --clean first "
                "(or --force to add more)."
            )
            await engine.dispose()
            return

        if args.dry_run:
            print("\n[DRY RUN] Plan:")
            for p in PERSONAS[:n_users]:
                print(
                    f"  Persona {p['id']:2d}  {p['name']:<26} "
                    f"noise={int(p['noise']*100):>2}%  dist={p['dist']}"
                )
            print(
                f"\n  Would create {n_users * args.bookings:,} bookings + passengers, "
                f"and write ground truth to {CSV_PATH}"
            )
            await engine.dispose()
            return

        print("\n  Loading real train pool (bucketed by distance + day/night)…")
        train_pool = await load_train_pool(session)
        for b in BUCKETS:
            print(
                f"    {b:<7} trains: {len(train_pool[b]['any']):>5}  "
                f"(day {len(train_pool[b]['day'])}, night {len(train_pool[b]['night'])})"
            )
        date_pool = build_date_pool()

        csv_rows = []
        total_b = total_bp = total_noise = 0
        pnr_counter = 1
        for u_idx, user in enumerate(users):
            persona = PERSONAS[u_idx]
            nb, nbp, noise = await seed_user(
                session,
                persona,
                user.id,
                u_idx,
                args.bookings,
                args.seed,
                args.test_frac,
                pnr_counter,
                train_pool,
                date_pool,
                csv_rows,
            )
            pnr_counter += nb
            total_b += nb
            total_bp += nbp
            total_noise += noise
            print(
                f"  [{persona['id']:2d}] {persona['name']:<26} "
                f"{nb:>4} bookings, {nbp:>4} pax rows, {noise:>3} noisy "
                f"({user.email})"
            )

        # write ground-truth CSV
        with open(CSV_PATH, "w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=list(csv_rows[0].keys()))
            writer.writeheader()
            writer.writerows(csv_rows)

    await engine.dispose()
    elapsed = time.time() - start
    print(f"\n{'=' * 64}")
    print(
        f"  Done in {elapsed:.1f}s — {total_b:,} bookings, {total_bp:,} passenger rows, "
        f"{total_noise:,} noisy ({total_noise / max(total_b,1) * 100:.1f}%)"
    )
    print(f"  Ground truth: {CSV_PATH}")
    print(f"{'=' * 64}\n")


if __name__ == "__main__":
    asyncio.run(main())
