# Level-2 Smart Autofill — train the global XGBoost train_class classifier.
#
# Pulls all (mock) bookings, builds leakage-free + time-aware features, trains a
# multi-class XGBoost model, evaluates it (baseline gate, train/test gap, per-class,
# confusion matrix, persona sanity), and saves a versioned artifact for inference.
#
# Usage:
#   APP_ENV=local ./venv/bin/python scripts/phase-2/train_autofill_class.py
#   APP_ENV=local ./venv/bin/python scripts/phase-2/train_autofill_class.py --test-size 0.2
import argparse
import asyncio
import json
import sys
import time
from collections import Counter, defaultdict, deque
from pathlib import Path

parser = argparse.ArgumentParser(description="Train the Level-2 autofill class model")
parser.add_argument("--test-size", type=float, default=0.2)
parser.add_argument("--seed", type=int, default=42)
parser.add_argument("--max-depth", type=int, default=5)
parser.add_argument("--n-estimators", type=int, default=300)
parser.add_argument("--learning-rate", type=float, default=0.08)
args = parser.parse_args()

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(_PROJECT_ROOT))

import joblib
import numpy as np
import pandas as pd
from sklearn.metrics import accuracy_score, classification_report, confusion_matrix
from sklearn.model_selection import train_test_split
from sklearn.utils.class_weight import compute_sample_weight
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from xgboost import XGBClassifier

from app.ai.pipelines.autofill_features import (
    CLASS_ORDER,
    CLASS_TO_IDX,
    FEATURE_ORDER,
    DISTANCE_WINDOW_KM,
    HIST_NONE,
    IDX_TO_CLASS,
    MODEL_VERSION,
    RECENCY_WINDOW,
    bucket_value_for_km,
    build_quota_codes,
    departure_hour,
    encode_row,
    hour_is_night,
    is_festival_month,
)
from app.db.base import DATABASE_URL, DB_SCHEMA

MODEL_DIR = _PROJECT_ROOT / "app" / "ai" / "models"
GROUND_TRUTH_CSV = Path(__file__).resolve().parent / "autofill_ground_truth.csv"
PNR_PREFIX = "M%"

DATA_SQL = text(
    f"""
    SELECT b.pnr_number AS pnr, b.user_id::text AS user_id,
           b.journey_date AS journey_date, b.booked_at AS booked_at,
           b.train_class AS actual_class, b.quota AS quota,
           abs(dst.distance_km - src.distance_km) AS distance_km,
           src.departure_time AS dep_time,
           pax.cnt AS passenger_count, pax.has_senior AS has_senior,
           pax.has_child AS has_child
    FROM {DB_SCHEMA}.bookings b
    JOIN {DB_SCHEMA}.train_stations src
      ON src.train_id = b.train_id AND src.station_id = b.source_station_id
    JOIN {DB_SCHEMA}.train_stations dst
      ON dst.train_id = b.train_id AND dst.station_id = b.destination_station_id
    JOIN LATERAL (
        SELECT count(*) AS cnt,
               bool_or(p.age >= 60) AS has_senior,
               bool_or(p.age < 12) AS has_child
        FROM {DB_SCHEMA}.booking_passengers bp
        JOIN {DB_SCHEMA}.passengers p ON p.id = bp.passenger_id
        WHERE bp.booking_id = b.id
    ) pax ON true
    WHERE b.pnr_number LIKE :prefix
    """
)


async def load_dataframe() -> pd.DataFrame:
    engine = create_async_engine(
        DATABASE_URL,
        connect_args={"server_settings": {"search_path": f'"{DB_SCHEMA}"'}},
    )
    Session = async_sessionmaker(
        bind=engine, class_=AsyncSession, expire_on_commit=False
    )
    async with Session() as s:
        rows = (await s.execute(DATA_SQL, {"prefix": PNR_PREFIX})).mappings().all()
    await engine.dispose()
    return pd.DataFrame(rows)


def add_base_features(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df["journey_date"] = pd.to_datetime(df["journey_date"])
    df["distance_km"] = df["distance_km"].astype(int)
    df["distance_bucket"] = df["distance_km"].apply(bucket_value_for_km)
    df["is_night_train"] = df["dep_time"].apply(
        lambda d: hour_is_night(departure_hour(d))
    )
    df["passenger_count"] = df["passenger_count"].astype(int)
    df["has_senior"] = df["has_senior"].fillna(False).astype(bool)
    df["has_child"] = df["has_child"].fillna(False).astype(bool)
    df["month"] = df["journey_date"].dt.month.astype(int)
    df["is_weekend"] = df["journey_date"].dt.weekday >= 5
    df["is_festival_season"] = df["month"].apply(is_festival_month)
    return df


def _nearby_mode(seen: list[tuple[int, str]], target_km: int) -> str:
    """Mode class among prior bookings within +/- DISTANCE_WINDOW_KM of target_km."""
    near = [c for km, c in seen if abs(km - target_km) <= DISTANCE_WINDOW_KM]
    return Counter(near).most_common(1)[0][0] if near else HIST_NONE


def add_time_aware_history(df: pd.DataFrame) -> pd.DataFrame:
    """user_hist_top_class / _class_for_bucket / _recent_class / _class_for_distance
    from each user's bookings STRICTLY BEFORE the current row's journey_date (no
    same-date leakage). recent = last RECENCY_WINDOW; distance = +/- window km."""
    df = df.sort_values(["user_id", "journey_date", "booked_at"]).copy()
    top_class: dict[int, str] = {}
    bucket_class: dict[int, str] = {}
    recent_class: dict[int, str] = {}
    distance_class: dict[int, str] = {}

    for _, group in df.groupby("user_id", sort=False):
        overall: Counter = Counter()
        by_bucket: dict[str, Counter] = defaultdict(Counter)
        recent: deque = deque(maxlen=RECENCY_WINDOW)
        seen_km: list[tuple[int, str]] = []
        for _, day_rows in group.groupby("journey_date", sort=True):
            overall_top = overall.most_common(1)[0][0] if overall else HIST_NONE
            recent_top = Counter(recent).most_common(1)[0][0] if recent else HIST_NONE
            for idx, row in day_rows.iterrows():
                b_counter = by_bucket[row["distance_bucket"]]
                top_class[idx] = overall_top
                bucket_class[idx] = (
                    b_counter.most_common(1)[0][0] if b_counter else HIST_NONE
                )
                recent_class[idx] = recent_top
                distance_class[idx] = _nearby_mode(seen_km, int(row["distance_km"]))
            for (
                _,
                row,
            ) in day_rows.iterrows():  # add after, so same date can't see itself
                overall[row["actual_class"]] += 1
                by_bucket[row["distance_bucket"]][row["actual_class"]] += 1
                recent.append(row["actual_class"])
                seen_km.append((int(row["distance_km"]), row["actual_class"]))

    df["user_hist_top_class"] = df.index.map(top_class)
    df["user_hist_class_for_bucket"] = df.index.map(bucket_class)
    df["user_hist_recent_class"] = df.index.map(recent_class)
    df["user_hist_class_for_distance"] = df.index.map(distance_class)
    return df


def build_xy(df: pd.DataFrame, encoders: dict):
    rows = df.to_dict("records")
    x = np.array([encode_row(r, encoders) for r in rows], dtype=float)
    y = np.array([CLASS_TO_IDX[r["actual_class"]] for r in rows], dtype=int)
    return x, y


def evaluate(model, x_train, y_train, x_test, y_test, test_df):
    print("\n" + "=" * 64)
    print("  EVALUATION (test set)")
    print("=" * 64)

    test_proba = model.predict_proba(x_test)
    test_pred = test_proba.argmax(axis=1)
    train_pred = model.predict(x_train)

    test_acc = accuracy_score(y_test, test_pred)
    train_acc = accuracy_score(y_train, train_pred)
    majority_idx = Counter(y_test.tolist()).most_common(1)[0][0]
    baseline = (y_test == majority_idx).mean()

    print(f"  Baseline (always '{IDX_TO_CLASS[majority_idx]}'): {baseline:.3f}")
    print(f"  Test accuracy:   {test_acc:.3f}")
    print(f"  Train accuracy:  {train_acc:.3f}")
    print(f"  Train-test gap:  {train_acc - test_acc:.3f}  (small = healthy)")
    print(f"  Beats baseline by: {test_acc - baseline:+.3f}")

    labels = list(range(len(CLASS_ORDER)))
    target_names = [IDX_TO_CLASS[i] for i in labels]
    print("\n  Per-class report:")
    print(
        classification_report(
            y_test,
            test_pred,
            labels=labels,
            target_names=target_names,
            zero_division=0,
            digits=3,
        )
    )
    print("  Confusion matrix (rows=true, cols=pred):")
    cm = confusion_matrix(y_test, test_pred, labels=labels)
    header = "        " + "".join(f"{n:>6}" for n in target_names)
    print(header)
    for i, row in enumerate(cm):
        print(f"  {target_names[i]:>5} " + "".join(f"{v:>6}" for v in row))

    persona_report = _persona_sanity(test_df, test_pred, test_proba, y_test)

    return {
        "baseline": round(float(baseline), 4),
        "test_accuracy": round(float(test_acc), 4),
        "train_accuracy": round(float(train_acc), 4),
        "train_test_gap": round(float(train_acc - test_acc), 4),
        "per_class": classification_report(
            y_test,
            test_pred,
            labels=labels,
            target_names=target_names,
            zero_division=0,
            output_dict=True,
        ),
        "persona_sanity": persona_report,
    }


def _persona_sanity(test_df, test_pred, test_proba, y_test) -> dict:
    if not GROUND_TRUTH_CSV.exists():
        print("\n  [persona] ground-truth CSV missing — skipping persona checks")
        return {}
    gt = pd.read_csv(GROUND_TRUTH_CSV)[["pnr", "persona_id", "persona"]]
    merged = test_df.reset_index(drop=True).merge(gt, on="pnr", how="left")
    merged["pred_idx"] = test_pred
    merged["pred_class"] = [IDX_TO_CLASS[i] for i in test_pred]
    merged["confidence"] = test_proba.max(axis=1)
    merged["correct"] = test_pred == y_test

    print("\n  Persona sanity (test rows):")
    report = {}
    for pid in sorted(merged["persona_id"].dropna().unique()):
        sub = merged[merged["persona_id"] == pid]
        name = sub["persona"].iloc[0]
        acc = sub["correct"].mean()
        conf = sub["confidence"].mean()
        top_pred = Counter(sub["pred_class"]).most_common(1)[0]
        report[int(pid)] = {
            "persona": name,
            "n": int(len(sub)),
            "accuracy": round(float(acc), 3),
            "mean_confidence": round(float(conf), 3),
            "top_pred": f"{top_pred[0]}({top_pred[1]})",
        }
        flag = ""
        if pid == 17:
            flag = "  <- expect LOW confidence"
        elif pid == 18:
            flag = "  <- expect recent class (3A)"
        elif pid in (6, 10, 11):
            flag = "  <- expect HIGH accuracy"
        print(
            f"   P{int(pid):2d} {name:<26} n={len(sub):<4} acc={acc:.2f} "
            f"conf={conf:.2f} top_pred={top_pred[0]}{flag}"
        )
    return report


async def main():
    start = time.time()
    print("=" * 64)
    print("  RailMind — Level-2 Autofill Class Trainer (XGBoost)")
    print("=" * 64)

    print("\n  Loading bookings + features from DB…")
    df = await load_dataframe()
    print(f"    {len(df):,} bookings loaded")

    df = add_base_features(df)
    df = add_time_aware_history(df)
    df = df[df["actual_class"].isin(CLASS_ORDER)].reset_index(drop=True)
    print(f"    {len(df):,} rows after feature build")
    print(f"    class mix: {dict(Counter(df['actual_class']))}")

    encoders = {
        "quota_codes": build_quota_codes(df["quota"].tolist()),
        "class_order": CLASS_ORDER,
        "feature_order": FEATURE_ORDER,
        "model_version": MODEL_VERSION,
    }

    x, y = build_xy(df, encoders)

    # stratified 80/20; rare classes (1A ~2%) present in both
    idx = np.arange(len(df))
    x_train, x_test, y_train, y_test, idx_train, idx_test = train_test_split(
        x, y, idx, test_size=args.test_size, random_state=args.seed, stratify=y
    )
    test_df = df.iloc[idx_test].reset_index(drop=True)

    # carve a validation set from train for early stopping (test stays untouched)
    x_tr, x_val, y_tr, y_val = train_test_split(
        x_train, y_train, test_size=0.15, random_state=args.seed, stratify=y_train
    )
    sample_weight = compute_sample_weight("balanced", y_tr)

    print(
        f"\n  Training XGBoost  (train={len(x_tr):,} val={len(x_val):,} test={len(x_test):,})"
    )
    model = XGBClassifier(
        objective="multi:softprob",
        num_class=len(CLASS_ORDER),
        max_depth=args.max_depth,
        n_estimators=args.n_estimators,
        learning_rate=args.learning_rate,
        subsample=0.8,
        colsample_bytree=0.8,
        min_child_weight=3,
        eval_metric="mlogloss",
        early_stopping_rounds=30,
        random_state=args.seed,
        n_jobs=-1,
    )
    model.fit(
        x_tr,
        y_tr,
        sample_weight=sample_weight,
        eval_set=[(x_val, y_val)],
        verbose=False,
    )
    print(f"    best_iteration={model.best_iteration} (early stopping)")

    metrics = evaluate(model, x_train, y_train, x_test, y_test, test_df)
    metrics["best_iteration"] = int(model.best_iteration)
    metrics["n_rows"] = int(len(df))
    metrics["features"] = FEATURE_ORDER

    # ── save artifacts ────────────────────────────────────────────────────────
    MODEL_DIR.mkdir(parents=True, exist_ok=True)
    stem = MODEL_VERSION.replace("autofill-class-", "autofill_class_")
    model_path = MODEL_DIR / f"{stem}.pkl"
    enc_path = MODEL_DIR / f"{stem}.encoders.json"
    metrics_path = MODEL_DIR / f"{stem}.metrics.json"
    joblib.dump(model, model_path)
    enc_path.write_text(json.dumps(encoders, indent=2))
    metrics_path.write_text(json.dumps(metrics, indent=2, default=float))

    print(f"\n{'=' * 64}")
    print(f"  Saved: {model_path.relative_to(_PROJECT_ROOT)}")
    print(f"         {enc_path.relative_to(_PROJECT_ROOT)}")
    print(f"         {metrics_path.relative_to(_PROJECT_ROOT)}")
    print(f"  Done in {time.time() - start:.1f}s")
    print(f"{'=' * 64}\n")


if __name__ == "__main__":
    asyncio.run(main())
