"""Inference for the Level-2 autofill train_class model.

Loads the versioned XGBoost artifact + encoders once and turns a raw feature dict
(built by AutofillModelService from leakage-free signals) into a class + confidence.
Pure CPU; no DB access here.
"""

from __future__ import annotations

import json
from pathlib import Path

from app.ai.pipelines.autofill_features import (
    IDX_TO_CLASS,
    MODEL_VERSION,
    encode_row,
)

MODEL_DIR = Path(__file__).resolve().parent.parent / "models"
_STEM = MODEL_VERSION.replace("autofill-class-", "autofill_class_")
MODEL_PATH = MODEL_DIR / f"{_STEM}.pkl"
ENCODERS_PATH = MODEL_DIR / f"{_STEM}.encoders.json"


class AutofillClassModel:
    """Lazy singleton around the trained classifier + its encoders."""

    _model = None
    _encoders: dict | None = None

    @classmethod
    def is_available(cls) -> bool:
        return MODEL_PATH.exists() and ENCODERS_PATH.exists()

    @classmethod
    def _load(cls) -> None:
        if cls._model is not None:
            return
        import joblib  # local import: keeps xgboost/joblib off the hot startup path

        cls._model = joblib.load(MODEL_PATH)
        cls._encoders = json.loads(ENCODERS_PATH.read_text())

    @classmethod
    def predict(cls, raw_features: dict) -> dict:
        """Returns {value, confidence, model_version}. confidence = max softprob."""
        cls._load()
        import numpy as np

        vector = encode_row(raw_features, cls._encoders)
        proba = cls._model.predict_proba(np.array([vector], dtype=float))[0]
        idx = int(proba.argmax())
        return {
            "value": IDX_TO_CLASS[idx],
            "confidence": round(float(proba[idx]), 2),
            "model_version": MODEL_VERSION,
        }
