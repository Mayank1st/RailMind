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

from app.ai.pipelines.waitlist_predictor_features import (
    CLASS_ORDER,
    FEATURE_ORDER,
    MODEL_VERSION,
    QUOTA_ORDER,
    TRAIN_TYPE_ORDER,
    WL_TYPE_ORDER,
    encode_row,
    is_festival_month,
)
from app.db.base import DATABASE_URL, DB_SCHEMA
from app.domain.waitlist.constants.waitlist_predictor import (
    BUCKET_HIGH_MIN,
    DEFAULT_ROUTE_CANCEL_RATE,
    MIN_HISTORY_FOR_CANCEL_RATE,
)

# ── config ────────────────────────────────────────────────────────────────────
PNR_PREFIX = "W"  # the contested-journey seed (seed_waitlist_bookings.py)
TEST_FRACTION = 0.2
SEED = 42
CONFIRM_EVAL_P = 0.50  # binary "will confirm" threshold for precision/recall
RELAX_P = BUCKET_HIGH_MIN  # the "relax / HIGH" line — its precision is the guardrail
PESSIMISM_WEIGHT = 0.65  # < 1: under-promise confirmation (asymmetric cost §6.4)

# Gate (precision-first, NOT accuracy — §6.5):
GATE_RELAX_PRECISION = 0.80  # when we say "relax", >=80% must actually confirm
GATE_CONFIRM_RECALL = 0.45  # but still catch a useful share of real confirmations

MODEL_DIR = _PROJECT_ROOT / "app" / "ai" / "models"
_STEM = MODEL_VERSION.replace("waitlist-predictor-", "waitlist_predictor_")
PKL_PATH = MODEL_DIR / f"{_STEM}.pkl"
ENCODERS_PATH = MODEL_DIR / f"{_STEM}.encoders.json"
METRICS_PATH = MODEL_DIR / f"{_STEM}.metrics.json"


async def load_entries(session) -> list[dict]:
    """Settled WL entries + leakage-free context. route_cancel_rate is the
    train+class cancel rate over past bookings (same quantity serving computes)."""
    sql = text(
        f"""
        WITH cr AS (
            SELECT train_id, train_class,
                   count(*) FILTER (
                       WHERE booking_status IN
                       ('CANCELLED','REFUND_PENDING','REFUND_COMPLETED')
                   ) AS canc,
                   count(*) AS n
            FROM {DB_SCHEMA}.bookings
            WHERE journey_date < CURRENT_DATE
            GROUP BY train_id, train_class
        )
        SELECT w.wl_type, w.booking_position AS pos, w.is_promoted,
               b.train_id, b.train_class AS cls, b.quota,
               b.journey_date AS jd,
               (b.journey_date - date(b.booked_at)) AS lead,
               t.train_type AS ttype, r.dist AS dist,
               cr.canc AS canc, cr.n AS cr_n
        FROM {DB_SCHEMA}.waitlists w
        JOIN {DB_SCHEMA}.booking_passengers bp ON bp.id = w.booking_passenger_id
        JOIN {DB_SCHEMA}.bookings b ON b.id = bp.booking_id
        JOIN {DB_SCHEMA}.trains t ON t.id = b.train_id
        JOIN (
            SELECT train_id, max(distance_km) AS dist
            FROM {DB_SCHEMA}.train_stations GROUP BY train_id
        ) r ON r.train_id = b.train_id
        LEFT JOIN cr ON cr.train_id = b.train_id AND cr.train_class = b.train_class
        WHERE b.pnr_number LIKE '{PNR_PREFIX}%'
          AND b.journey_date < CURRENT_DATE
        """
    )
    return [dict(r._mapping) for r in (await session.execute(sql)).fetchall()]


def to_raw(r: dict) -> dict:
    cr_n = int(r["cr_n"]) if r["cr_n"] is not None else 0
    if cr_n >= MIN_HISTORY_FOR_CANCEL_RATE and r["canc"] is not None:
        route_cancel_rate = int(r["canc"]) / cr_n
    else:
        route_cancel_rate = DEFAULT_ROUTE_CANCEL_RATE
    jd = r["jd"]
    return {
        "wl_position": int(r["pos"]),
        "wl_type": r["wl_type"],
        "days_to_journey": max(0, int(r["lead"])),
        "train_class": r["cls"],
        "quota": r["quota"],
        "train_type": r["ttype"] or "EXPRESS",
        "distance_km": int(r["dist"]) if r["dist"] else 0,
        "route_cancel_rate": route_cancel_rate,
        "month": jd.month,
        "is_weekend": jd.weekday() >= 5,
        "is_festival_season": is_festival_month(jd.month),
    }


def split_by_journey(rows: list[dict], rng: random.Random) -> tuple[list, list]:
    """Journey-level split (no train/journey context leaks across train/test)."""
    by_key: dict = defaultdict(list)
    for r in rows:
        by_key[(r["train_id"], r["jd"], r["cls"], r["quota"])].append(r)
    keys = list(by_key)
    rng.shuffle(keys)
    n_test = int(len(keys) * TEST_FRACTION)
    test_keys = set(keys[:n_test])
    train, test = [], []
    for k, group in by_key.items():
        (test if k in test_keys else train).extend(group)
    return train, test


def build_xy(rows: list[dict]) -> tuple[list, list]:
    X = [encode_row(to_raw(r)) for r in rows]
    y = [1 if r["is_promoted"] else 0 for r in rows]
    return X, y


async def main() -> None:
    start = time.time()
    print("=" * 64)
    print("  RailMind — Waitlist Predictor L2 Trainer (Phase 2)")
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
        rows = await load_entries(session)
    await engine.dispose()

    if not rows:
        print(
            "\n[ERROR] No settled W-prefix WL entries. Run seed_waitlist_bookings.py first."
        )
        return

    pos = sum(1 for r in rows if r["is_promoted"])
    pos_rate = pos / len(rows)
    print(f"\n  Settled WL entries : {len(rows):,}")
    print(f"  P(confirm)         : {100*pos_rate:.1f}%  (CNF+RAC)")
    print(
        f"  Majority baseline  : {100*max(pos_rate, 1-pos_rate):.1f}% accuracy "
        f"(but 'always confirm' strands every real WL — wrong metric, §6.5)"
    )
    if pos == 0 or pos == len(rows):
        print("\n[ERROR] Single-class labels — cannot train.")
        return

    rng = random.Random(SEED)
    train_rows, test_rows = split_by_journey(rows, rng)
    Xtr, ytr = build_xy(train_rows)
    Xte, yte = build_xy(test_rows)
    print(f"\n  Train rows         : {len(Xtr):,}  (test {len(Xte):,})")

    Xtr_a, ytr_a = np.array(Xtr, float), np.array(ytr)
    Xte_a, yte_a = np.array(Xte, float), np.array(yte)
    pos_tr = int(ytr_a.sum())
    neg_tr = len(ytr) - pos_tr
    balance = neg_tr / pos_tr if pos_tr else 1.0
    spw = balance * PESSIMISM_WEIGHT  # < balance -> reluctant to predict "confirm"
    print(f"  class balance neg/pos : {balance:.2f}")
    print(
        f"  scale_pos_weight      : {spw:.2f}  (= balance * {PESSIMISM_WEIGHT} pessimism)"
    )

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

    proba = model.predict_proba(Xte_a)[:, 1]

    # General confirm precision/recall at the binary line.
    pred = (proba >= CONFIRM_EVAL_P).astype(int)
    tn, fp, fn, tp = confusion_matrix(yte_a, pred, labels=[0, 1]).ravel()
    precision = precision_score(yte_a, pred, zero_division=0)
    recall = recall_score(yte_a, pred, zero_division=0)
    accuracy = (tp + tn) / len(yte_a)

    # The safety guardrail: precision of the "relax / HIGH" call (proba >= RELAX_P).
    relax_pred = proba >= RELAX_P
    relax_n = int(relax_pred.sum())
    relax_tp = int(((relax_pred) & (yte_a == 1)).sum())
    relax_precision = relax_tp / relax_n if relax_n else 0.0
    false_confirm_rate = 1.0 - precision  # §6.4.4 guardrail

    print(f"\n  ── Test metrics ──")
    print(
        f"  confirm precision @{CONFIRM_EVAL_P:.2f} : {precision:.3f}   (when we say confirm, right?)"
    )
    print(
        f"  confirm recall    @{CONFIRM_EVAL_P:.2f} : {recall:.3f}   (of real confirms, caught)"
    )
    print(
        f"  false-confirm rate         : {false_confirm_rate:.3f}   (guardrail — keep low)"
    )
    print(
        f"  RELAX precision   @{RELAX_P:.2f} : {relax_precision:.3f}   (PRIMARY — when we say relax, right?)  n={relax_n}"
    )
    print(f"  accuracy                   : {accuracy:.3f}")
    print(f"  confusion [tn fp / fn tp]  : [{tn} {fp} / {fn} {tp}]")

    gate = (
        "PASS"
        if relax_precision >= GATE_RELAX_PRECISION and recall >= GATE_CONFIRM_RECALL
        else "REVIEW"
    )
    print(
        f"  baseline gate              : {gate}  "
        f"(relax_precision>={GATE_RELAX_PRECISION} & confirm_recall>={GATE_CONFIRM_RECALL})"
    )

    MODEL_DIR.mkdir(parents=True, exist_ok=True)
    joblib.dump(model, PKL_PATH)
    ENCODERS_PATH.write_text(
        json.dumps(
            {
                "model_version": MODEL_VERSION,
                "feature_order": FEATURE_ORDER,
                "confirm_eval_p": CONFIRM_EVAL_P,
                "relax_p": RELAX_P,
                "wl_type_order": WL_TYPE_ORDER,
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
                "positive_rate": round(pos_rate, 4),
                "scale_pos_weight": round(spw, 3),
                "precision": round(float(precision), 4),
                "recall": round(float(recall), 4),
                "relax_precision": round(relax_precision, 4),
                "relax_n": relax_n,
                "false_confirm_rate": round(false_confirm_rate, 4),
                "accuracy": round(float(accuracy), 4),
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
