# Waitlist Confirmation Predictor — contested-journey seeder (Phase 2, Feature 03).
#
# WHY a separate seeder (vs the fare-advisor / autofill ones):
#   The fare seeder writes per-JOURNEY demand curves but NO passengers and NO
#   `waitlists` rows — so its 14.5k WAITLISTED bookings are hollow (status only,
#   no wl_type / position / promotion outcome). The Waitlist Predictor needs the
#   one thing none of them produced: real `waitlists` entries with a *settled
#   outcome* (promoted to CNF/RAC, or auto-cancelled at chart) so the L2 label
#   (is_promoted; see planning doc §6.1) and the L1 position/wl_type signals are
#   learnable. (Gate run on 2026-06-28: 3 waitlists rows, 0 settled — L2 dead.)
#
# DESIGN (planning doc §6):
#   * A journey = (train, train_class, quota, journey_date). Capacity + the live
#     seat_inventories row already exist (16M rows) — we read & update them.
#   * Only OVERSUBSCRIBED journeys (load > 1) are kept — they alone have a queue.
#   * Outcome is EMERGENT from a simulated cancellation -> promotion process, not
#     a formula-on-the-label (avoids the autofill-P18 / §6.5 artifact trap where
#     the model just relearns the label generator):
#       - cancel_count = round(cancel_rate * capacity), cancel_rate from OBSERVABLE
#         features (train_type, class, season, distance) + i.i.d. noise — no hidden
#         per-train constant the model can't see.
#       - The WL queue is ordered by IRCTC priority (GNWL > RLWL > PQWL > RQWL),
#         freed CNF seats promote the front, then RAC slots take the next band.
#         TQWL NEVER reaches RAC (Phase-1 fact) — only direct CNF from a tiny
#         Tatkal cancellation pool; the rest auto-cancel.
#       - Per-entry jitter on the ordering => labels aren't perfectly monotonic in
#         position (quota pools cancel unevenly) — genuine, learnable noise.
#   * route_cancel_rate signal: each journey writes its confirmed fill with
#     `cancel_count` of the holders CANCELLED (no passengers needed — only the
#     status feeds the rate). Comparable W-volume per train lifts the train+class
#     cancel-rate above the cancellation-free D-bookings.
#   * Past-biased dates so charts have "run" => settled labels. A few future
#     journeys stay live (WAITLISTED) to exercise the serving path.
#
# Scope notes:
#   * Train-level WL (no boarding->alighting segment) — planning doc §9 v1.
#   * PNR prefix "W" so --clean targets only these (D = demand, M = autofill).
#   * Reuses the 193 mock passengers + mock users; seat_inventories are UPDATED
#     in place (not created) to the simulated fill.
#
# Usage:
#   APP_ENV=local ./venv/bin/python scripts/phase-2/seed_waitlist_bookings.py
#   APP_ENV=local ./venv/bin/python scripts/phase-2/seed_waitlist_bookings.py --journeys 300
#   APP_ENV=local ./venv/bin/python scripts/phase-2/seed_waitlist_bookings.py --clean
#   APP_ENV=local ./venv/bin/python scripts/phase-2/seed_waitlist_bookings.py --dry-run
import argparse
import asyncio
import sys
import time
import uuid
from collections import Counter
from datetime import date, datetime, time as dtime, timedelta, timezone
from pathlib import Path

parser = argparse.ArgumentParser(
    description="Seed contested-journey WL bookings + waitlist outcomes (Feature 03)"
)
parser.add_argument(
    "--journeys", type=int, default=1500, help="number of contested journeys to seed"
)
parser.add_argument("--seed", type=int, default=42, help="base RNG seed (reproducible)")
parser.add_argument(
    "--clean", action="store_true", help="delete W-prefix WL bookings + their waitlists"
)
parser.add_argument(
    "--force", action="store_true", help="seed even if W bookings already exist"
)
parser.add_argument(
    "--dry-run", action="store_true", help="print the plan and exit without writing"
)
args = parser.parse_args()

import random

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(_PROJECT_ROOT))

from sqlalchemy import delete, select, text, tuple_, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.db.base import DATABASE_URL, DB_SCHEMA
from app.db.models.booking import BookingPassengers, Bookings
from app.db.models.train import SeatInventories
from app.db.models.user import Users
from app.db.models.waiting_list import WaitlistEntries
from app.domain.booking.constants.booking import BookingStatus, PassengerStatus
from app.utils.helpers import get_utc_timezone

# ── identifiers / scope ───────────────────────────────────────────────────────
MOCK_EMAIL_LIKE = "mock.user%@railmind.test"
PNR_PREFIX = "W"  # waitlist bookings: W000000001 ..

# ── date window (relative to today) ───────────────────────────────────────────
PAST_DAYS = 120  # settled journeys -> L2 labels
FUTURE_DAYS = 18  # a few live WL journeys -> serving path
PAST_BIAS = 0.88  # heavily past so most outcomes are charted/settled

# ── class mix + capacity fallback (real capacity comes from seat_inventories) ──
CLASS_WEIGHTS = {"SL": 0.36, "3A": 0.28, "2A": 0.12, "CC": 0.12, "2S": 0.08, "1A": 0.04}
CAPACITY_FALLBACK = {"SL": 72, "3A": 64, "2A": 46, "1A": 24, "CC": 78, "2S": 108}
WL_MAX = 200

# ── quota mix ─────────────────────────────────────────────────────────────────
QUOTA_WEIGHTS = {"GN": 0.82, "TQ": 0.18}

# ── WL-type mix within a GN queue (TQ journeys are all TQWL) ───────────────────
GN_WL_TYPE_WEIGHTS = {"GNWL": 0.60, "RLWL": 0.18, "PQWL": 0.16, "RQWL": 0.06}
# IRCTC promotion priority — lower rank promotes first (planning doc §5/§7).
PRIORITY_RANK = {"GNWL": 0, "RLWL": 1, "PQWL": 2, "RQWL": 3, "TQWL": 9}

# ── demand model — load factor (queue length) from OBSERVABLE features + noise ─
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
LOAD_FESTIVAL_MULT = 1.30
LOAD_WEEKEND_MULT = 1.15
BASE_LOAD = 1.28  # >1 median so a healthy fraction is contested (deeper queues)

# ── cancellation model — route_cancel_rate driver, OBSERVABLE + noise ─────────
# Festivals REDUCE cancellations (people travel) -> WL stays stuck (planning §6.2).
BASE_CANCEL_RATE = 0.22
TYPE_CANCEL = {
    "RAJDHANI": 0.85,
    "SHATABDI": 0.85,
    "DURONTO": 0.90,
    "GARIB_RATH": 1.05,
    "JAN_SHATABDI": 1.05,
    "SUPERFAST": 1.0,
    "EXPRESS": 1.10,
    "PASSENGER": 1.25,
}
CLASS_CANCEL = {
    "SL": 1.20,
    "2S": 1.20,
    "3E": 1.05,
    "3A": 1.0,
    "CC": 1.0,
    "2A": 0.85,
    "FC": 0.8,
    "1A": 0.70,
}
CANCEL_FESTIVAL_MULT = 0.70
CANCEL_NOISE = (0.70, 1.30)
CANCEL_MIN, CANCEL_MAX = 0.03, 0.55
TQ_CANCEL_FRACTION = 0.25  # Tatkal pool that frees up (TQWL -> direct CNF only)
# Not every cancellation promotes a live WL — no-shows, post-chart cancels and
# blocked/quota-locked seats mean only a fraction of freed seats reach the queue.
# Keeps P(confirm) realistic (vs ~72% if every cancellation promoted) and the
# label balanced enough for L2 (planning doc §6.5).
PROMOTION_EFFICIENCY = 0.72

# ── fare model (rough INR; realistic ordering) ────────────────────────────────
BASE_FARE = {"2S": 25, "SL": 45, "CC": 90, "3A": 130, "2A": 220, "1A": 420}
PER_KM = {"2S": 0.55, "SL": 0.75, "CC": 1.6, "3A": 1.95, "2A": 2.7, "1A": 4.5}
LEAD_MEAN = 18.0
MAX_LEAD = 60


def now_utc() -> datetime:
    return get_utc_timezone()


def compute_fare(train_class: str, dist_km: int) -> float:
    return float(
        round(BASE_FARE.get(train_class, 60) + PER_KM.get(train_class, 1.0) * dist_km)
    )


def weighted_choice(weights: dict, rng: random.Random) -> str:
    keys = list(weights)
    return rng.choices(keys, weights=[weights[k] for k in keys], k=1)[0]


def load_factor(train_type: str, jd: date, dist: int, rng: random.Random) -> float:
    fest = LOAD_FESTIVAL_MULT if jd.month in FESTIVAL_MONTHS else 1.0
    wknd = LOAD_WEEKEND_MULT if jd.weekday() >= 5 else 1.0
    dist_mult = 1.10 if dist > 1000 else (0.95 if dist < 400 else 1.0)
    return (
        BASE_LOAD
        * TYPE_DEMAND.get(train_type, 1.0)
        * fest
        * wknd
        * dist_mult
        * rng.uniform(0.75, 1.70)
    )


def cancel_rate(train_type: str, cls: str, jd: date, rng: random.Random) -> float:
    fest = CANCEL_FESTIVAL_MULT if jd.month in FESTIVAL_MONTHS else 1.0
    r = (
        BASE_CANCEL_RATE
        * TYPE_CANCEL.get(train_type, 1.0)
        * CLASS_CANCEL.get(cls, 1.0)
        * fest
        * rng.uniform(*CANCEL_NOISE)
    )
    return max(CANCEL_MIN, min(CANCEL_MAX, r))


def draw_lead(rng: random.Random) -> int:
    return min(int(rng.expovariate(1.0 / LEAD_MEAN)), MAX_LEAD)


# ── data loaders ──────────────────────────────────────────────────────────────
async def load_train_pool(session) -> list[dict]:
    sql = text(
        f"""
        SELECT t.id AS train_id, t.source_station_id AS src,
               t.destination_station_id AS dst, t.train_type AS ttype, r.dist AS dist
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


async def get_passenger_ids(session) -> list:
    rows = (
        await session.execute(text(f"SELECT id FROM {DB_SCHEMA}.passengers"))
    ).fetchall()
    return [r.id for r in rows]


async def fetch_inventories(session, keys: list[tuple]) -> dict:
    """Map (train_id, jd, class, quota) -> (inv_id, capacity, rac_slots, wl_max)
    for the journeys we picked. seat_inventories already exist for every journey."""
    out: dict = {}
    for i in range(0, len(keys), 1000):
        chunk = keys[i : i + 1000]
        k = tuple_(
            SeatInventories.train_id,
            SeatInventories.journey_date,
            SeatInventories.train_class,
            SeatInventories.quota,
        )
        stmt = select(
            SeatInventories.id,
            SeatInventories.train_id,
            SeatInventories.journey_date,
            SeatInventories.train_class,
            SeatInventories.quota,
            SeatInventories.total_confirmed_seats,
            SeatInventories.total_rac_slots,
            SeatInventories.wl_max,
        ).where(k.in_(chunk))
        for r in (await session.execute(stmt)).all():
            out[(r.train_id, r.journey_date, r.train_class, r.quota)] = (
                r.id,
                int(r.total_confirmed_seats),
                int(r.total_rac_slots),
                int(r.wl_max),
            )
    return out


def build_journeys(
    train_pool: list[dict], n: int, today: date, rng: random.Random
) -> list[dict]:
    seen, journeys, attempts = set(), [], 0
    while len(journeys) < n and attempts < n * 6:
        attempts += 1
        train = rng.choice(train_pool)
        cls = weighted_choice(CLASS_WEIGHTS, rng)
        quota = weighted_choice(QUOTA_WEIGHTS, rng)
        if rng.random() < PAST_BIAS:
            jd = today - timedelta(days=rng.randint(2, PAST_DAYS))
        else:
            jd = today + timedelta(days=rng.randint(1, FUTURE_DAYS))
        key = (train["train_id"], cls, quota, jd)
        if key in seen:
            continue
        seen.add(key)
        journeys.append({"train": train, "class": cls, "quota": quota, "jd": jd})
    return journeys


# ── the simulation ────────────────────────────────────────────────────────────
def simulate(
    journey: dict,
    capacity: int,
    rac_slots: int,
    wl_max: int,
    today: date,
    rng: random.Random,
) -> dict | None:
    """Return per-journey plan: holder fill (CONFIRMED/CANCELLED counts) + a list
    of WL entries with their settled outcome, or None if not contested."""
    train, cls, quota, jd = (
        journey["train"],
        journey["class"],
        journey["quota"],
        journey["jd"],
    )
    is_past = jd < today

    load = load_factor(train["ttype"], jd, train["dist"], rng)
    queue_len = round((load - 1.0) * capacity)
    if queue_len < 1:
        return None  # not contested — no waitlist to model
    # WL can never exceed the inventory's wl_max (and our global WL_MAX cap).
    queue_len = min(queue_len, WL_MAX, wl_max if wl_max > 0 else WL_MAX)

    r = cancel_rate(train["ttype"], cls, jd, rng)
    cancel_count = round(r * capacity)

    if quota == "TQ":
        types = ["TQWL"] * queue_len
        # tiny Tatkal pool, and only a fraction of it actually promotes
        freed_cnf = round(cancel_count * TQ_CANCEL_FRACTION * PROMOTION_EFFICIENCY)
        rac_avail = 0  # TQWL never reaches RAC
    else:
        types = [weighted_choice(GN_WL_TYPE_WEIGHTS, rng) for _ in range(queue_len)]
        freed_cnf = round(cancel_count * PROMOTION_EFFICIENCY)
        rac_avail = rac_slots

    # One effective clearance queue, ordered by IRCTC priority (GNWL first), then
    # arrival, with small jitter (uneven quota pools). booking_position is the
    # GLOBAL rank in this queue; current_position is the live rank after promotions
    # — so current_position <= booking_position always (a WL only moves UP).
    entries = [{"wl_type": t, "_arrival": i} for i, t in enumerate(types)]
    entries.sort(
        key=lambda e: (
            PRIORITY_RANK[e["wl_type"]],
            e["_arrival"] + rng.uniform(-1.5, 1.5),
        )
    )
    for rank, e in enumerate(entries, start=1):
        e["booking_position"] = rank

    cnf_left, rac_left, live_pos = freed_cnf, rac_avail, 0
    for e in entries:
        if cnf_left > 0:
            e.update(is_promoted=True, promoted_to="CNF", current_position=0)
            cnf_left -= 1
        elif rac_left > 0 and e["wl_type"] != "TQWL":
            e.update(is_promoted=True, promoted_to="RAC", current_position=0)
            rac_left -= 1
        else:
            live_pos += 1
            e.update(is_promoted=False, promoted_to=None, current_position=live_pos)

    return {
        "is_past": is_past,
        "capacity": capacity,
        "cancel_count": cancel_count,
        "rac_used": rac_avail - rac_left,
        "cnf_promoted": freed_cnf - cnf_left,
        "wl_entries": entries,
        "remaining_wl": live_pos,
    }


async def clean(session) -> None:
    # waitlists cascade on bookings delete (FK ondelete CASCADE), but delete
    # explicitly first for a clean count, then the bookings.
    bp_subq = (
        select(BookingPassengers.id)
        .join(Bookings, Bookings.id == BookingPassengers.booking_id)
        .where(Bookings.pnr_number.like(f"{PNR_PREFIX}%"))
    )
    wl = await session.execute(
        delete(WaitlistEntries).where(WaitlistEntries.booking_passenger_id.in_(bp_subq))
    )
    bk = await session.execute(
        delete(Bookings).where(Bookings.pnr_number.like(f"{PNR_PREFIX}%"))
    )
    await session.commit()
    print(
        f"\n  Deleted {wl.rowcount} waitlist entries + {bk.rowcount} W-bookings "
        f"(booking_passengers cascade with bookings)."
    )
    print("  (seat_inventories fills left as-is; a re-seed overwrites them.)")


async def main() -> None:
    start = time.time()
    print("=" * 66)
    print("  RailMind — Waitlist Predictor Contested-Journey Seeder (Phase 2)")
    print("=" * 66)

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
            await clean(session)
        await engine.dispose()
        print(f"\n  Done in {time.time() - start:.1f}s\n")
        return

    rng = random.Random(args.seed)
    today = date.today()

    async with async_session() as session:
        user_ids = await get_mock_user_ids(session)
        passenger_ids = await get_passenger_ids(session)
        if not user_ids or not passenger_ids:
            print(
                "\n[ERROR] Need mock users + passengers. Run seed_mock_users.py first."
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
                "\n[ABORT] W-bookings already exist. Run with --clean first (or --force)."
            )
            await engine.dispose()
            return

        print(f"\n  Schema:   {DB_SCHEMA}")
        print(
            f"  Journeys: {args.journeys:,} requested  |  window today-{PAST_DAYS}d..+{FUTURE_DAYS}d  (past {PAST_BIAS})"
        )
        print(
            f"  Reuse:    {len(user_ids)} mock users, {len(passenger_ids)} passengers"
        )
        print("\n  Loading real train pool…")
        train_pool = await load_train_pool(session)
        print(f"    {len(train_pool):,} trains (50-2500 km)")
        if not train_pool:
            print("\n[ERROR] No trains found.")
            await engine.dispose()
            return

        journeys = build_journeys(train_pool, args.journeys, today, rng)
        inv_map = await fetch_inventories(
            session,
            [
                (j["train"]["train_id"], j["jd"], j["class"], j["quota"])
                for j in journeys
            ],
        )
        print(
            f"    {len(journeys):,} journeys picked, {len(inv_map):,} with a live inventory row"
        )

        booking_rows, bp_rows, wl_rows, inv_updates = [], [], [], []
        pnr = 1
        contested = 0
        outcome_counter: Counter = Counter()
        wl_type_counter: Counter = Counter()
        wl_type_confirm: Counter = Counter()

        for j in journeys:
            key = (j["train"]["train_id"], j["jd"], j["class"], j["quota"])
            inv = inv_map.get(key)
            if inv is None:
                continue
            inv_id, capacity, rac_slots, wl_max = inv
            if capacity <= 0:
                capacity = CAPACITY_FALLBACK.get(j["class"], 60)
            plan = simulate(j, capacity, rac_slots, wl_max, today, rng)
            if plan is None:
                continue
            contested += 1
            train = j["train"]
            fare = compute_fare(j["class"], train["dist"])
            chart_ts = datetime.combine(
                j["jd"], dtime(0, 0), tzinfo=timezone.utc
            ) - timedelta(hours=4)

            # 1. Confirmed-holder fill (no passengers): some CONFIRMED, some CANCELLED.
            #    Feeds route_cancel_rate; the CANCELLED are the seats that freed up.
            confirmed_holders = max(0, capacity - plan["cancel_count"])
            for idx in range(capacity):
                lead = draw_lead(rng)
                booked_at = datetime.combine(
                    j["jd"] - timedelta(days=lead), dtime(10, 0), tzinfo=timezone.utc
                )
                if booked_at > now_utc():
                    booked_at = now_utc() - timedelta(days=1)
                status = (
                    BookingStatus.CONFIRMED.value
                    if idx < confirmed_holders
                    else BookingStatus.CANCELLED.value
                )
                booking_rows.append(
                    _booking_row(
                        pnr, rng.choice(user_ids), train, j, fare, status, booked_at
                    )
                )
                pnr += 1

            # 2. WL bookings + passengers + waitlist entries (the heart of it).
            for e in plan["wl_entries"]:
                lead = draw_lead(rng)
                booked_at = datetime.combine(
                    j["jd"] - timedelta(days=lead), dtime(10, 30), tzinfo=timezone.utc
                )
                if booked_at > now_utc():
                    booked_at = now_utc() - timedelta(hours=6)

                if e["is_promoted"]:
                    b_status = (
                        BookingStatus.CONFIRMED.value
                        if e["promoted_to"] == "CNF"
                        else BookingStatus.RAC.value
                    )
                    p_status = (
                        PassengerStatus.CONFIRMED.value
                        if e["promoted_to"] == "CNF"
                        else PassengerStatus.RAC.value
                    )
                    promoted_at, auto_cancelled, auto_at = chart_ts, False, None
                elif plan["is_past"]:
                    b_status, p_status = (
                        BookingStatus.CANCELLED.value,
                        PassengerStatus.AUTO_CANCELLED_CHART.value,
                    )
                    promoted_at, auto_cancelled, auto_at = None, True, chart_ts
                else:
                    b_status, p_status = (
                        BookingStatus.WAITLISTED.value,
                        PassengerStatus.WAITLISTED.value,
                    )
                    promoted_at, auto_cancelled, auto_at = None, False, None

                outcome_counter[
                    e["promoted_to"]
                    or ("AUTO_CANCELLED" if auto_cancelled else "STILL_WL")
                ] += 1
                wl_type_counter[e["wl_type"]] += 1
                if e["is_promoted"]:
                    wl_type_confirm[e["wl_type"]] += 1

                booking_id = uuid.uuid4()
                bp_id = uuid.uuid4()
                booking_rows.append(
                    _booking_row(
                        pnr,
                        rng.choice(user_ids),
                        train,
                        j,
                        fare,
                        b_status,
                        booked_at,
                        booking_id,
                    )
                )
                bp_rows.append(
                    {
                        "id": bp_id,
                        "booking_id": booking_id,
                        "seat_inventory_id": inv_id,
                        "passenger_id": rng.choice(passenger_ids),
                        "seat_id": None,
                        "berth_preference": "NP",
                        "allotted_berth": None,
                        "passenger_status": p_status,
                        "fare": fare,
                        "is_active": True,
                        "created_at": booked_at,
                        "updated_at": booked_at,
                    }
                )
                wl_rows.append(
                    {
                        "id": uuid.uuid4(),
                        "booking_id": booking_id,
                        "booking_passenger_id": bp_id,
                        "seat_inventory_id": inv_id,
                        "train_class": j["class"],
                        "quota": j["quota"],
                        "wl_type": e["wl_type"],
                        "booking_position": e["booking_position"],
                        "current_position": e["current_position"],
                        "source_station_id": train["src"],
                        "destination_station_id": train["dst"],
                        "is_promoted": e["is_promoted"],
                        "promoted_to": e["promoted_to"],
                        "promoted_at": promoted_at,
                        "is_auto_cancelled": auto_cancelled,
                        "auto_cancelled_at": auto_at,
                        "is_active": True,
                        "created_at": booked_at,
                        "updated_at": booked_at,
                    }
                )
                pnr += 1

            # 3. Inventory counters consistent with the simulated fill.
            #    A live (future) journey with WL left is oversubscribed by definition
            #    -> confirmed & RAC are FULL (available = 0), else the seat-availability
            #    view would show AVAILABLE while a waitlist exists (contradiction).
            cnf_total = confirmed_holders + plan["cnf_promoted"]
            remaining_wl = 0 if plan["is_past"] else min(plan["remaining_wl"], wl_max)
            if remaining_wl > 0:
                available_cnf, available_rac = 0, 0
            else:
                available_cnf = max(0, capacity - cnf_total)
                available_rac = max(0, rac_slots - plan["rac_used"])
            inv_updates.append(
                {
                    "id": inv_id,
                    "available_confirmed_seats": available_cnf,
                    "available_rac_slots": available_rac,
                    "wl_count": remaining_wl,
                    "is_chart_prepared": plan["is_past"],
                    "chart_status": (
                        "FINAL_PREPARED" if plan["is_past"] else "NOT_PREPARED"
                    ),
                }
            )

        if args.dry_run:
            print(
                f"\n[DRY RUN] {contested:,} contested journeys; would write "
                f"{len(booking_rows):,} bookings, {len(wl_rows):,} waitlist entries. Nothing written."
            )
            _print_gate(outcome_counter, wl_type_counter, wl_type_confirm, len(wl_rows))
            await engine.dispose()
            return

        # asyncpg caps a statement at 32767 bind params -> keep cols*rows under it
        # (waitlists has 19 cols; 19 * 1500 = 28,500 < 32,767).
        BATCH = 1500
        print(
            f"\n  Writing {len(booking_rows):,} bookings, {len(bp_rows):,} passengers, "
            f"{len(wl_rows):,} waitlist entries across {contested:,} journeys…"
        )
        for i in range(0, len(booking_rows), BATCH):
            await session.execute(
                pg_insert(Bookings).values(booking_rows[i : i + BATCH])
            )
        for i in range(0, len(bp_rows), BATCH):
            await session.execute(
                pg_insert(BookingPassengers).values(bp_rows[i : i + BATCH])
            )
        for i in range(0, len(wl_rows), BATCH):
            await session.execute(
                pg_insert(WaitlistEntries).values(wl_rows[i : i + BATCH])
            )
        for i in range(0, len(inv_updates), 1000):
            for row in inv_updates[i : i + 1000]:
                await session.execute(
                    update(SeatInventories)
                    .where(SeatInventories.id == row["id"])
                    .values(
                        available_confirmed_seats=row["available_confirmed_seats"],
                        available_rac_slots=row["available_rac_slots"],
                        wl_count=row["wl_count"],
                        is_chart_prepared=row["is_chart_prepared"],
                        chart_status=row["chart_status"],
                    )
                )
        await session.commit()

    await engine.dispose()
    print(f"\n{'=' * 66}")
    print(f"  Done in {time.time() - start:.1f}s")
    print(f"  Contested journeys : {contested:,}")
    print(f"  Bookings written   : {len(booking_rows):,}")
    print(f"  Waitlist entries   : {len(wl_rows):,}")
    _print_gate(outcome_counter, wl_type_counter, wl_type_confirm, len(wl_rows))
    print(f"{'=' * 66}\n")


def _booking_row(
    pnr, user_id, train, j, fare, status, booked_at, booking_id=None
) -> dict:
    return {
        "id": booking_id or uuid.uuid4(),
        "user_id": user_id,
        "train_id": train["train_id"],
        "pnr_number": f"{PNR_PREFIX}{pnr:09d}",
        "booking_status": status,
        "journey_date": j["jd"],
        "source_station_id": train["src"],
        "destination_station_id": train["dst"],
        "train_class": j["class"],
        "quota": j["quota"],
        "total_fare": fare,
        "booked_at": booked_at,
        "is_active": True,
        "created_at": booked_at,
        "updated_at": booked_at,
    }


def _print_gate(
    outcome_counter: Counter,
    wl_type_counter: Counter,
    wl_type_confirm: Counter,
    total_wl: int,
) -> None:
    """The §6.5 viability numbers — printed so the L2 go/no-go is obvious."""
    if not total_wl:
        print("\n  [GATE] No waitlist entries produced.")
        return
    confirmed = outcome_counter.get("CNF", 0) + outcome_counter.get("RAC", 0)
    print(f"\n  ── §6.5 GATE (label balance) ──")
    print(f"  WL entries (label rows)  : {total_wl:,}")
    print(f"  P(confirm, CNF+RAC)      : {100.0 * confirmed / total_wl:.1f}%")
    print("  outcomes:")
    for k, v in outcome_counter.most_common():
        print(f"    {k:16s}: {v:7,d}  ({100.0 * v / total_wl:5.1f}%)")
    print("  P(confirm) by wl_type (GNWL should lead, TQWL trail):")
    for k, v in wl_type_counter.most_common():
        rate = 100.0 * wl_type_confirm.get(k, 0) / v if v else 0.0
        print(f"    {k:6s}: {v:7,d} rows  confirm {rate:5.1f}%")


if __name__ == "__main__":
    asyncio.run(main())
