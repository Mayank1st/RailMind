from typing import Optional

from app.schemas.base import BaseDTO


# -- AdvisorToggleItem (one advisor card) ------------------------
class AdvisorToggleItemDTO(BaseDTO):
    advisor_key: str  # fare | waitlist | autofill
    name: str  # "Waitlist Predictor"
    description: str
    state: str  # OFF | FORCE_RULES | ON (toggle position)
    state_label: str  # "Off" | "Force rules" | "On"
    model_version: Optional[str]  # from the metrics file, e.g. "fare-advisor-v1"
    model_available: bool  # artifact present + loadable
    serving: str  # ml | rules | off (what's ACTUALLY served now)
    status: str  # live | degraded | off (badge / banner driver)
    metrics: dict  # curated headline metrics from the metrics file
    metrics_summary: str  # "Precision 0.95 · Recall 0.94"
