import asyncio
import json
import sys
import time
from collections import defaultdict
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(_PROJECT_ROOT))

import random

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

try:
    import joblib
    import numpy as np
    import xgboost as xgb
    from sklearn.metrics import confusion_matrix, precision_score, recall_score
except ImportError as _ml_import_error:
    print(
        f"\n[ERROR] ML deps missing ({_ml_import_error}). "
        "Need xgboost + scikit-learn (+ libomp on macOS)."
    )
    sys.exit(1)

from app.ai.pipelines.fare_advisor_features import (
    FEATURE_ORDER,
    MODEL_VERSION,
    CLASS_ORDER,
    QUOTA_ORDER,
    TRAIN_TYPE_ORDER,
    encode_row,
    is_festival_month,
)
from app.db.base import DATABASE_URL, DB_SCHEMA
from app.domain.fare.constants.fare_advisor import (
    BOOK_NOW_HORIZON_DAYS,
    BOOK_NOW_P,
    VELOCITY_WINDOW_DAYS,
)

# ── config ────────────────────────────────────────────────────────────────────
PNR_PREFIX = "D"
SNAPSHOT_LEADS = [1, 2, 3, 5, 7, 10, 15, 20, 30]  # decision moments per journey
W = BOOK_NOW_HORIZON_DAYS
WL_MAX = 200
CAPACITY = {"SL": 72, "3A": 64, "2A": 46, "1A": 24, "CC": 78, "2S": 108}
TEST_FRACTION = 0.2
SEED = 42

MODEL_DIR = _PROJECT_ROOT / "app" / "ai" / "models"
_STEM = MODEL_VERSION.replace("fare-advisor-", "fare_advisor_")  # fare_advisor_v1
PKL_PATH = MODEL_DIR / f"{_STEM}.pkl"
ENCODERS_PATH = MODEL_DIR / f"{_STEM}.encoders.json"
METRICS_PATH = MODEL_DIR / f"{_STEM}.metrics.json"


async def load_bookings(session) -> list[dict]:
    sql = text(
        f"""
        SELECT b.train_id, b.train_class AS cls, b.quota,
               b.journey_date AS jd,
               (b.journey_date - date(b.booked_at)) AS lead,
               b.booking_status AS status,
               t.train_type AS ttype, r.dist AS dist,
               inv.total_confirmed_seats AS capacity
        FROM {DB_SCHEMA}.bookings b
        JOIN {DB_SCHEMA}.trains t ON t.id = b.train_id
        JOIN (
            SELECT train_id, max(distance_km) AS dist
            FROM {DB_SCHEMA}.train_stations GROUP BY train_id
        ) r ON r.train_id = b.train_id
        LEFT JOIN {DB_SCHEMA}.seat_inventories inv
            ON inv.train_id = b.train_id AND inv.journey_date = b.journey_date
           AND inv.train_class = b.train_class AND inv.quota = b.quota
        WHERE b.pnr_number LIKE '{PNR_PREFIX}%'
        """
    )
    return [dict(r._mapping) for r in (await session.execute(sql)).fetchall()]


def group_journeys(rows: list[dict]) -> dict:
    """Group bookings into journeys with their curve + static context."""
    journeys: dict = defaultdict(lambda: {"leads": [], "wl_leads": []})
    for r in rows:
        key = (r["train_id"], r["cls"], r["quota"], r["jd"])
        j = journeys[key]
        lead = int(r["lead"])
        j["leads"].append(lead)
        if r["status"] == "WAITLISTED":
            j["wl_leads"].append(lead)
        # static context (same across the journey's rows)
        j["ttype"] = r["ttype"] or "EXPRESS"
        j["dist"] = int(r["dist"])
        j["cls"] = r["cls"]
        j["quota"] = r["quota"]
        j["jd"] = r["jd"]
        j["capacity"] = (
            int(r["capacity"]) if r["capacity"] else CAPACITY.get(r["cls"], 72)
        )
    return journeys


def build_rows(journeys: dict) -> tuple[list, list, list]:
    """Return (X, y, is_contested) over all journey×snapshot rows (leakage-free)."""
    X, y, contested_flags = [], [], []
    for key, j in journeys.items():
        leads = j["leads"]
        capacity = max(1, j["capacity"])
        sellout_lead = max(j["wl_leads"]) if j["wl_leads"] else None
        jd = j["jd"]
        for d in SNAPSHOT_LEADS:
            # leakage-free as-of-d signals (only bookings made on/before d)
            cum = sum(1 for L in leads if L >= d)
            confirmed = min(cum, capacity)
            wl = max(0, cum - capacity)
            velocity = sum(1 for L in leads if d <= L < d + VELOCITY_WINDOW_DAYS)

            # label (§8.1 horizon-W)
            if sellout_lead is None:
                label = 0
            else:
                margin = d - sellout_lead
                if margin < 0:
                    continue  # already gone -> URGENT rule, exclude from model
                label = 1 if margin <= W else 0

            raw = {
                "fill_rate": confirmed / capacity,
                "booking_velocity": velocity,
                "waitlist_pressure": wl / WL_MAX,
                "days_to_journey": d,
                "distance_km": j["dist"],
                "train_type": j["ttype"],
                "quota": j["quota"],
                "train_class": j["cls"],
                "month": jd.month,
                "is_weekend": jd.weekday() >= 5,
                "is_festival_season": is_festival_month(jd.month),
            }
            X.append(encode_row(raw))
            y.append(label)
            contested_flags.append(sellout_lead is not None)
    return X, y, contested_flags


def split_by_journey(journeys: dict, rng: random.Random) -> tuple[set, set]:
    keys = list(journeys.keys())
    rng.shuffle(keys)
    n_test = int(len(keys) * TEST_FRACTION)
    test = set(keys[:n_test])
    return set(keys[n_test:]), test


async def main() -> None:
    start = time.time()
    print("=" * 64)
    print("  RailMind — Fare Advisor L2 Trainer (Phase 2)")
    print("=" * 64)

    engine = create_async_engine(
        DATABASE_URL,
        echo=False,
        connect_args={"server_settings": {"search_path": f'"{DB_SCHEMA}"'}},
    )
    async_session = async_sessionmaker(
        bind=engine, class_=AsyncSession, expire_on_commit=False
    )
    async with async_session() as session:
        rows = await load_bookings(session)
    await engine.dispose()

    if not rows:
        print(
            "\n[ERROR] No demand (D-prefix) bookings. Run seed_fare_advisor_bookings.py first."
        )
        return

    journeys = group_journeys(rows)
    contested = sum(1 for j in journeys.values() if j["wl_leads"])
    print(f"\n  Bookings loaded   : {len(rows):,}")
    print(f"  Distinct journeys : {len(journeys):,}")
    print(f"  Contested (WL)    : {contested:,}  ({100*contested/len(journeys):.1f}%)")

    # ── deterministic journey-level split, then build rows per side ───────────
    rng = random.Random(SEED)
    train_keys, test_keys = split_by_journey(journeys, rng)
    Xtr, ytr, _ = build_rows({k: journeys[k] for k in train_keys})
    Xte, yte, cte = build_rows({k: journeys[k] for k in test_keys})

    pos_tr = sum(ytr)
    pos_rate = pos_tr / len(ytr) if ytr else 0
    print(f"\n  Training rows     : {len(Xtr):,}  (test {len(Xte):,})")
    print(f"  Positive (BOOK_NOW): {pos_tr:,}  ({100*pos_rate:.1f}%)")
    print(
        f"  Majority baseline : {100*max(pos_rate, 1-pos_rate):.1f}% accuracy "
        f"(but 'always CAN_WAIT' catches 0% of sellouts — wrong metric, §8.5)"
    )
    if pos_tr == 0:
        print(
            "\n[ERROR] No positive labels — cannot train. Seed more contested journeys."
        )
        return

    Xtr_a, ytr_a = np.array(Xtr, float), np.array(ytr)
    Xte_a, yte_a = np.array(Xte, float), np.array(yte)
    neg, pos = len(ytr) - pos_tr, pos_tr
    spw = neg / pos  # §8.3 strong bias toward catching sellouts
    print(f"  scale_pos_weight  : {spw:.2f}")

    model = xgb.XGBClassifier(
        objective="binary:logistic",
        eval_metric="aucpr",
        n_estimators=300,
        max_depth=5,
        learning_rate=0.08,
        subsample=0.9,
        colsample_bytree=0.9,
        scale_pos_weight=spw,
        early_stopping_rounds=30,
        random_state=SEED,
    )
    model.fit(Xtr_a, ytr_a, eval_set=[(Xte_a, yte_a)], verbose=False)

    # ── evaluate at the safe-biased serving threshold (§8.3/§8.6) ─────────────
    proba = model.predict_proba(Xte_a)[:, 1]
    pred = (proba >= BOOK_NOW_P).astype(int)
    tn, fp, fn, tp = confusion_matrix(yte_a, pred, labels=[0, 1]).ravel()
    recall = recall_score(yte_a, pred, zero_division=0)
    precision = precision_score(yte_a, pred, zero_division=0)
    false_book_now = fp / (tp + fp) if (tp + fp) else 0.0  # §8.3.4 guardrail
    accuracy = (tp + tn) / len(yte_a)

    print(f"\n  ── Test metrics @ threshold {BOOK_NOW_P} ──")
    print(
        f"  sellout recall (PRIMARY) : {recall:.3f}   (of true BOOK_NOW, how many caught)"
    )
    print(f"  precision                : {precision:.3f}")
    print(
        f"  false-BOOK_NOW rate      : {false_book_now:.3f}   (guardrail — keep well under ~0.6)"
    )
    print(f"  accuracy                 : {accuracy:.3f}")
    print(f"  confusion [tn fp / fn tp]: [{tn} {fp} / {fn} {tp}]")

    gate = "PASS" if recall >= 0.6 and false_book_now <= 0.6 else "REVIEW"
    print(f"  baseline gate            : {gate}  (recall>=0.60 & false-BOOK_NOW<=0.60)")

    # ── persist artifact ──────────────────────────────────────────────────────
    MODEL_DIR.mkdir(parents=True, exist_ok=True)
    joblib.dump(model, PKL_PATH)
    ENCODERS_PATH.write_text(
        json.dumps(
            {
                "model_version": MODEL_VERSION,
                "feature_order": FEATURE_ORDER,
                "snapshot_leads": SNAPSHOT_LEADS,
                "horizon_w": W,
                "book_now_p": BOOK_NOW_P,
                "train_type_order": TRAIN_TYPE_ORDER,
                "quota_order": QUOTA_ORDER,
                "class_order": CLASS_ORDER,
            },
            indent=2,
        )
    )
    METRICS_PATH.write_text(
        json.dumps(
            {
                "model_version": MODEL_VERSION,
                "rows_train": len(Xtr),
                "rows_test": len(Xte),
                "positive_rate_train": round(pos_rate, 4),
                "scale_pos_weight": round(spw, 3),
                "threshold": BOOK_NOW_P,
                "recall": round(recall, 4),
                "precision": round(precision, 4),
                "false_book_now_rate": round(false_book_now, 4),
                "accuracy": round(accuracy, 4),
                "confusion": {
                    "tn": int(tn),
                    "fp": int(fp),
                    "fn": int(fn),
                    "tp": int(tp),
                },
                "gate": gate,
            },
            indent=2,
        )
    )
    print(f"\n  Saved: {PKL_PATH.name}, {ENCODERS_PATH.name}, {METRICS_PATH.name}")
    print(f"\n  Done in {time.time() - start:.1f}s\n")


if __name__ == "__main__":
    asyncio.run(main())
