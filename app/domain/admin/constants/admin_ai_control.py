from app.core.advisor_flags import AdvisorKey, AdvisorState

# ─── Error codes (RM-ADMIN-AI-NNN) ────────────────────────────────────────────

ERR_ADVISOR_NOT_FOUND = "RM-ADMIN-AI-001"

# ─── State labels (segmented toggle) ──────────────────────────────────────────

STATE_LABELS = {
    AdvisorState.OFF.value: "Off",
    AdvisorState.FORCE_RULES.value: "Force rules",
    AdvisorState.ON.value: "On",
}

DEFAULT_ADVISOR_STATE = AdvisorState.ON.value

# ─── Serving / status (derived for the badge + degraded banner) ───────────────

SERVING_ML = "ml"
SERVING_RULES = "rules"
SERVING_OFF = "off"

STATUS_LIVE = "live"  # ML actually serving
STATUS_DEGRADED = "degraded"  # wanted ML but serving rules (force-rules or model down)
STATUS_OFF = "off"

# ─── Advisor registry — display + which metrics file to read ──────────────────
# `metrics_stem` → app/ai/models/<stem>.metrics.json. `metric_fields` picks the
# (json_key, label) pairs shown in the card's metrics line. Order = UI order.

ADVISOR_REGISTRY: dict[str, dict] = {
    AdvisorKey.WAITLIST.value: {
        "name": "Waitlist Predictor",
        "description": "Estimates confirmation probability for WL tickets.",
        "metrics_stem": "waitlist_predictor_v1",
        "metric_fields": [("precision", "Precision"), ("recall", "Recall")],
    },
    AdvisorKey.FARE.value: {
        "name": "Fare Advisor",
        "description": "Book-now vs wait guidance (BOOK_NOW / CAN_WAIT / URGENT).",
        "metrics_stem": "fare_advisor_v1",
        "metric_fields": [("precision", "Precision"), ("recall", "Recall")],
    },
    AdvisorKey.AUTOFILL.value: {
        "name": "Autofill",
        "description": "Predicts a user's likely class & quota at search.",
        "metrics_stem": "autofill_class_v2",
        "metric_fields": [("test_accuracy", "Accuracy"), ("baseline", "Baseline")],
    },
    AdvisorKey.CANCELLATION.value: {
        "name": "Cancellation Advisor",
        "description": (
            "Refund preview + cancel-or-wait advice; reuses the Waitlist "
            "Predictor for WL bookings."
        ),
        # No artifact of its own — the ML half is the reused waitlist model.
        "metrics_stem": "waitlist_predictor_v1",
        "metric_fields": [("precision", "Precision"), ("recall", "Recall")],
    },
}

# Display order (matches the mockup).
ADVISOR_ORDER = list(ADVISOR_REGISTRY.keys())
