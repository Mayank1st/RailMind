"""Read a trained model's sidecar metrics file (app/ai/models/<stem>.metrics.json).

Used by the admin AI Control screen to surface model_version + headline metrics
without loading the model artifact itself. Cached — metrics files are static.
"""

import json
from datetime import date, datetime, timezone
from functools import lru_cache
from pathlib import Path
from typing import Optional

_MODELS_DIR = Path(__file__).resolve().parent / "models"


@lru_cache(maxsize=32)
def load_model_metrics(stem: str) -> dict:
    """Return the parsed <stem>.metrics.json, or {} if missing/unreadable."""
    path = _MODELS_DIR / f"{stem}.metrics.json"
    try:
        with path.open() as handle:
            return json.load(handle)
    except Exception:
        return {}


def artifact_exists(stem: str) -> bool:
    """True if the trained model artifact <stem>.pkl is present on disk."""
    return (_MODELS_DIR / f"{stem}.pkl").exists()


def artifact_trained_at(stem: str) -> Optional[date]:
    """Best-effort 'trained on' date = the artifact file's mtime (no training
    timestamp is recorded in the metrics file). None if the file is missing."""
    try:
        mtime = (_MODELS_DIR / f"{stem}.pkl").stat().st_mtime
        return datetime.fromtimestamp(mtime, tz=timezone.utc).date()
    except Exception:
        return None
