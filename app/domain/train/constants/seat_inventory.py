# ── Rolling window job ─────────────────────────────────────────────────────
ROLLING_WINDOW_DAYS_AHEAD = 120

# ── Retention / prune job ───────────────────────────────────────────────────
INVENTORY_RETENTION_DAYS = 7

SEAT_INVENTORY_BATCH_SIZE = 500

# ── Beat schedule (IST — celery timezone is Asia/Kolkata) ──────────────────
SEAT_INVENTORY_EXTEND_HOUR = 2
SEAT_INVENTORY_EXTEND_MINUTE = 30
SEAT_INVENTORY_PRUNE_HOUR = 3
SEAT_INVENTORY_PRUNE_MINUTE = 30

# Per-coach confirmed-seat count, keyed by train_class — mirrors the coach/seat
SEAT_CONFIG: dict[str, dict[str, int]] = {
    "SL": {"confirmed_seats": 65},
    "3A": {"confirmed_seats": 60},
    "2A": {"confirmed_seats": 43},
    "1A": {"confirmed_seats": 24},
    "CC": {"confirmed_seats": 78},
    "2S": {"confirmed_seats": 108},
}

QUOTA_ALLOCATION: dict[str, dict[str, int]] = {
    "SL": {"GN": 70, "TQ": 20, "LD": 3, "HP": 2, "DF": 2, "SS": 2, "FT": 1},
    "3A": {"GN": 70, "TQ": 20, "LD": 2, "HP": 2, "DF": 2, "SS": 3, "FT": 1},
    "2A": {"GN": 70, "TQ": 20, "LD": 2, "HP": 2, "DF": 2, "SS": 3, "FT": 1},
    "1A": {"GN": 70, "TQ": 20, "LD": 0, "HP": 2, "DF": 4, "SS": 3, "FT": 1},
    "CC": {"GN": 75, "TQ": 20, "LD": 2, "HP": 1, "DF": 1, "SS": 1, "FT": 0},
    "2S": {"GN": 80, "TQ": 15, "LD": 2, "HP": 1, "DF": 1, "SS": 1, "FT": 0},
}

WL_MAX: dict[str, int] = {
    "GN": 200,
    "TQ": 50,
    "PT": 50,
    "LD": 20,
    "HP": 20,
    "DF": 20,
    "SS": 20,
    "FT": 10,
}

RAC_BERTHS_PER_COACH: dict[str, int] = {
    "SL": 7,
    "3A": 4,
    "2A": 3,
    "1A": 0,
    "CC": 0,
    "2S": 0,
    "FC": 0,
    "3E": 2,
}
