# Smart Autofill — Level 2 model artifacts

Global **XGBoost** classifier that predicts a booking's `train_class`
(`SL / 3A / 2S / 2A / CC / 1A`). Used by the hybrid `/api/v1/ai/form/smart-autofill`
endpoint: users with `> MODEL_MIN_BOOKINGS` (10) bookings get the model; everyone
else stays on Level-1 rules. Confidence (max softprob) drives the existing
`AI_CONFIDENCE_THRESHOLD = 0.75` → `auto_fill`.

## Files (one versioned artifact set)

| File | Purpose |
|------|---------|
| `autofill_class_v2.pkl` | trained `XGBClassifier` (joblib) |
| `autofill_class_v2.encoders.json` | quota codes, class order, feature order, `model_version` |
| `autofill_class_v2.metrics.json` | test accuracy, per-class, persona sanity (per trained version) |

### Versions

- **v2 (current):** added `user_hist_class_for_distance` (mode within ±250 km — finer
  than the bucket) **and** split the `LONG` distance bucket at 1500 km (`LONG` 1000–1500,
  `XLONG` >1500). Fixes the "class boundary inside a coarse bucket" miss — e.g. an
  AC-Only user at 1438 km now predicts `3A` (their real choice) instead of `2A`, while
  >1500 km correctly stays `2A`. 2A precision 0.52→0.55.
- **v1:** baseline model (12 features, 3 distance buckets). Superseded.

Feature engineering is shared between training and inference in
`app/ai/pipelines/autofill_features.py` (single source of truth — no train/serve skew).

## Retrain

```bash
APP_ENV=local ./venv/bin/python scripts/phase-2/train_autofill_class.py
```

Trains on the seeded bookings, evaluates (baseline gate, train/test gap, per-class,
confusion matrix, persona sanity), and overwrites the `v1` artifact. Bump
`MODEL_VERSION` in `autofill_features.py` for a new version.

**v2 metrics:** test accuracy ≈ **0.705** vs majority baseline **0.418**; train/test gap
≈ **0.03** (healthy, no overfitting). Rare classes kept via `balanced` sample weights.

## ⚠️ Runtime requirement — OpenMP

`xgboost` needs the OpenMP runtime to load:

- **macOS (dev):** `brew install libomp`
- **Docker / Linux:** `libgomp1` (already added to the runtime stage in `Dockerfile`)

Without it, `import xgboost` fails and the model path errors. The endpoint only
reaches the model when the artifact exists *and* the user clears the booking
threshold — if the artifact is missing it falls back to Level-1 rules cleanly, but a
missing `libgomp1` will surface as a 500 on the model path.

## Deploy / artifact location

The `.pkl` is **committed to git** for now: deploy is a Docker build that `COPY . .`s
the repo into the image (`.dockerignore` keeps `app/ai/models/*.pkl`), so the artifact
ships with the image. There is no separate artifact pipeline yet.

> **TODO (v2):** move artifacts to object storage (GCS bucket) and download at
> startup, so model versions aren't tied to git history. Convert to **ONNX**
> (`skl2onnx` / `onnxmltools`) for lighter, `libomp`-free inference.

## Known limitation — persona #18 (Recency Shifter) on mock data

The mock seeder created P18's SL→3A taste shift by **generation order (`i`)**, but
`journey_date` and `booked_at` were assigned randomly — so the shift is **not encoded
in any time column** the model can see. Result: P18 predicts the cumulative majority
(`SL`), not the recent class (`3A`), on mock data.

This is a **data artifact, not a model bug**. The recency feature
(`user_hist_recent_class`, mode over the user's last `RECENCY_WINDOW=20` bookings) is
implemented correctly and is demonstrably influential (flipping only the recent-class
input moves the prediction confidence substantially). On **real** data — where
`booked_at` is naturally chronological — recency works as intended. We deliberately
did **not** patch the seeder to fake this signal.
