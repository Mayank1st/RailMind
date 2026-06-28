from __future__ import annotations

from pathlib import Path

from app.ai.pipelines.waitlist_predictor_features import MODEL_VERSION, encode_row

MODEL_DIR = Path(__file__).resolve().parent.parent / "models"
_STEM = MODEL_VERSION.replace("waitlist-predictor-", "waitlist_predictor_")
MODEL_PATH = MODEL_DIR / f"{_STEM}.pkl"
ENCODERS_PATH = MODEL_DIR / f"{_STEM}.encoders.json"


class WaitlistPredictorModel:
    """Lazy singleton around the trained P(WL -> CNF/RAC) classifier."""

    _model = None

    @classmethod
    def is_available(cls) -> bool:
        return MODEL_PATH.exists() and ENCODERS_PATH.exists()

    @classmethod
    def _load(cls) -> None:
        if cls._model is not None:
            return
        import joblib  # local import: keeps xgboost/joblib off the hot startup path

        cls._model = joblib.load(MODEL_PATH)

    @classmethod
    def predict_confirm_proba(cls, raw_features: dict) -> float:
        """P(this waitlist entry reaches CNF or RAC). 0.0-1.0."""
        return cls.predict_confirm_proba_batch([raw_features])[0]

    @classmethod
    def predict_confirm_proba_batch(cls, raw_list: list[dict]) -> list[float]:
        """Batched P(confirm) — one predict_proba call for N entries."""
        if not raw_list:
            return []
        cls._load()
        import numpy as np

        matrix = np.array([encode_row(r) for r in raw_list], dtype=float)
        proba = cls._model.predict_proba(matrix)
        return [float(p[1]) for p in proba]
