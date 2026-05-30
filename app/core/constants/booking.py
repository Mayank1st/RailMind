from enum import Enum

# ─── Booking Limits ───────────────────────────────────────────────────────────

MAX_PASSENGERS_PER_BOOKING = 6
MAX_PASSENGERS_PER_TATKAL_BOOKING = 4
MAX_ADVANCE_BOOKING_DAYS = 120
TATKAL_BOOKING_OPEN_HOUR = 10  # 10:00 AM IST
PREMIUM_TATKAL_OPEN_HOUR = 10
MIN_BOOKING_AGE_YEARS = 5
MAX_CHILD_AGE_YEARS = 12
WAITLIST_AUTO_PROMOTE_BATCH_SIZE = 50
WAITLIST_MAX_POSITION = 200
WL_PROMOTION_PRIORITY_ORDER: list[str] = ["GNWL", "RLWL", "PQWL"]

# ─── Chart Preparation ────────────────────────────────────────────────────────

# How many hours before scheduled departure each chart stage is prepared.
# Stage 1 (first chart): berth assignments begin, first WL → RAC promotions.
# Stage 2 (final chart): remaining WL auto-cancelled, quota releases happen.
CHART_STAGE_1_HOURS_BEFORE = 8
CHART_STAGE_2_HOURS_BEFORE = 4  # The "4 hours before departure" rule

# Quotas whose unused berths are released to the GN pool at chart preparation.
# Released berths become available for WL → RAC → CNF promotion.
RELEASABLE_QUOTAS_AT_CHART: list[str] = ["LD", "HP", "DF", "SS", "FT"]

# ─── Tatkal Quota Allocation ──────────────────────────────────────────────────

TATKAL_SEAT_ALLOCATION_PERCENT = 20  # 20% of seats per class reserved for TQ


class BookingStatus(str, Enum):
    INITIATED = "initiated"
    CONFIRMED = "confirmed"
    WAITLISTED = "waitlisted"
    RAC = "rac"
    CANCELLED = "cancelled"
    REFUND_PENDING = "refund_pending"
    REFUND_COMPLETED = "refund_completed"


class BerthPreference(str, Enum):
    LOWER = "LB"
    MIDDLE = "MB"
    UPPER = "UB"
    SIDE_LOWER = "SL"
    SIDE_UPPER = "SU"
    NO_PREFERENCE = "NP"


# ─── Seat Matrix ──────────────────────────────────────────────────────────────


class PassengerStatus(str, Enum):
    """
    Fine-grained status for a single passenger within a booking.
    Distinct from BookingStatus which tracks the booking as a whole.
    """

    CONFIRMED = "CNF"
    RAC = "RAC"
    WAITLISTED = "WL"
    CANCELLED = "CAN"


class BookingAvailabilityStatus(str, Enum):
    """
    What type of booking is currently possible for a given
    (train, date, class, quota) combination.

    Determined by SeatInventory.booking_status property at query time.
    """

    AVAILABLE = "AVAILABLE"  # Confirmed seats remain
    RAC = "RAC"  # Confirmed exhausted; RAC slots remain
    WL = "WL"  # RAC exhausted; waitlist still open
    REGRET = "REGRET"  # Waitlist full — no booking possible


class WaitlistType(str, Enum):
    """
    Waitlist sub-type, determined at booking time by the passenger's
    source-destination pair relative to the train route.

    Promotion priority order (highest → lowest):
        GNWL > RLWL > PQWL > TQWL

    Key behavioural differences:
        GNWL — most seats allocated here; highest cancellation volume
        RLWL — own quota per remote station; lower volume
        PQWL — shared small pool across minor intermediate stations
        TQWL — bypasses RAC entirely; direct CNF or auto-cancel+full-refund
        RQWL — request quota edge cases
    """

    GNWL = "GNWL"  # General Waiting List  (origin → terminus, or near-origin)
    RLWL = "RLWL"  # Remote Location WL    (designated mid-route city as source)
    PQWL = "PQWL"  # Pooled Quota WL       (between two intermediate stations)
    TQWL = "TQWL"  # Tatkal WL             (Tatkal quota exhausted)
    RQWL = "RQWL"  # Request WL            (edge cases / special quotas)


# ─── RAC Configuration ────────────────────────────────────────────────────────

# Number of physical side-lower berths earmarked as RAC per coach, by class.
# Each physical berth accommodates 2 RAC passengers (shared seating).
# Source: Railway Board circular (ICF/LHB coach standards).
#
#   total_rac_slots = RAC_BERTHS_PER_COACH[class] × 2
#
RAC_BERTHS_PER_COACH: dict[str, int] = {
    "SL": 7,  # 7 berths → 14 RAC passenger slots
    "3A": 4,  # 4 berths → 8  RAC passenger slots
    "2A": 3,  # 3 berths → 6  RAC passenger slots
    "1A": 0,  # First AC — no RAC
    "CC": 0,  # Chair car — no RAC
    "2S": 0,  # Second sitting — no RAC
    "FC": 0,  # First class — no RAC
    "3E": 2,  # Economy AC 3-tier — 2 berths → 4 RAC passenger slots
}


class JourneyActionType(str, Enum):
    UPCOMING = "UPCOMING"
    PAST = "PAST"
