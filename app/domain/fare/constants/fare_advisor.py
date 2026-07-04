from enum import Enum

# ── Error code ────────────────────────────────────────────────────────────────
# Advisor must never block the booking flow — every failure logs under this code
# and the endpoint degrades to a safe default (graceful degradation).
ERROR_CODE_ADVISOR = "RM-FARE-ADV-001"

# ── Fill-rate thresholds (fraction of confirmed seats already taken) ───────────
# fill_rate = (total_confirmed - available_confirmed) / total_confirmed
URGENT_FILL_RATE = 0.90  # >= this -> seats almost gone
# fill_rate == 1.0 iff available_confirmed_seats == 0 (sold out — only RAC/WL left).
SOLD_OUT_FILL_RATE = 1.0  # >= this -> confirmed seats gone, only RAC/WL booking
BOOK_NOW_FILL_RATE = 0.70  # >= this -> filling fast, don't wait
CAN_WAIT_FILL_RATE = 0.40  # < this (with time in hand) -> safe to wait

# ── Days-to-journey bands ─────────────────────────────────────────────────────
NEAR_JOURNEY_DAYS = 3  # at/under this, high demand tips to BOOK_NOW
FAR_JOURNEY_DAYS = 10  # beyond this, low fill can safely wait

# ── Booking velocity (recent bookings for the same journey) ───────────────────
VELOCITY_WINDOW_DAYS = 2  # look-back window for "recent" bookings
VELOCITY_HIGH_PER_DAY = 10  # >= this many/day -> HIGH demand
VELOCITY_MODERATE_PER_DAY = 5  # >= this many/day -> MODERATE demand

# ── Confidence levels (how sure the rule is — drives soft vs firm UI) ──────────
CONFIDENCE_DECIMALS = 2
CONFIDENCE_HIGH = 0.9  # certain (already waitlisting / seats gone)
CONFIDENCE_MEDIUM = 0.6  # indirect signal (velocity + proximity)
CONFIDENCE_LOW = (
    0.4  # at the threshold (borderline) / no live signal -> honest "not sure"
)
# L1 confidence for fill-rate decisions scales with distance from the threshold:
# at the boundary -> LOW; this many fill-rate points past it -> HIGH.
CONFIDENCE_FILL_SPAN = 0.20

# ── L2 label horizon (days) — see planning doc §8.1 ───────────────────────────
# BOOK_NOW iff the journey sells out within this many days of the decision point;
# beyond it -> CAN_WAIT (don't cry wolf). URGENT sub-band when sellout is imminent.
BOOK_NOW_HORIZON_DAYS = 5
URGENT_HORIZON_DAYS = 2

# ── L2 serving threshold (safe-biased; see planning doc §8.3/§8.6) ────────────
# P(sells-out-within-W) >= this -> BOOK_NOW; else CAN_WAIT. Starting guess 0.30,
# tune on the precision/recall tradeoff (don't pair a strong scale_pos_weight
# with an aggressive threshold — that double-biases into always-BOOK_NOW).
BOOK_NOW_P = 0.30

# ── Holiday-aware reason (display-only; NOT a decision/model input) ────────────
HOLIDAY_LOOKAHEAD_DAYS = 7
HOLIDAY_LOOKBEHIND_DAYS = 2

# ── High-fill safety floor (serving overlay; asymmetric cost §8.3) ─────────────
# A near-full journey is risky enough to NEVER advise waiting, even if the model
# (reading slow recent demand) predicts no imminent sellout — a wrong CAN_WAIT at
# high fill loses the user's seat. Below URGENT_FILL_RATE but at/above this, the
# model's CAN_WAIT is clamped up to BOOK_NOW. (L1 already does this via its
# BOOK_NOW_FILL_RATE rule; this keeps the model path consistent.)
BOOK_NOW_FLOOR_FILL_RATE = 0.85


class AdvisorDecision(str, Enum):
    BOOK_NOW = "BOOK_NOW"
    CAN_WAIT = "CAN_WAIT"
    URGENT = "URGENT"


class BookingVelocity(str, Enum):
    HIGH = "HIGH"
    MODERATE = "MODERATE"
    LOW = "LOW"


class AdvisorSource(str, Enum):
    RULES = "RULES"
    MODEL = "MODEL"
