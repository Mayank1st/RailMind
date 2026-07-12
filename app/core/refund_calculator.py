from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


# ─── CNF cancellation slabs (hours before scheduled departure) ────────────────
# > 48h            → flat cancellation charge per passenger (per class)
# 48h – 12h        → 25% of fare, subject to the flat-charge minimum
# 12h – 4h         → 50% of fare, subject to the flat-charge minimum
# < 4h / post-chart → no refund on online cancellation

CNF_FLAT_MIN_HOURS = 48.0
CNF_QUARTER_MIN_HOURS = 12.0
CNF_HALF_MIN_HOURS = 4.0

CNF_QUARTER_DEDUCTION_RATE = 0.25
CNF_HALF_DEDUCTION_RATE = 0.50

# ─── Flat cancellation charge per passenger, by class (₹) ─────────────────────
# Rules 2015, Rule 6 — the "> 48h" flat charge and the minimum for the
# percentage slabs.

FLAT_CANCELLATION_CHARGE: dict[str, int] = {
    "1A": 240,
    "EC": 240,
    "FC": 200,
    "2A": 200,
    "3A": 180,
    "3E": 180,
    "CC": 180,
    "SL": 120,
    "2S": 60,
}
FLAT_CANCELLATION_CHARGE_DEFAULT = 60

# ─── RAC / WL cancellation ────────────────────────────────────────────────────
# Cancellable up to 30 min before departure for a flat clerkage per passenger;
# after that, no online refund.

CLERKAGE_CHARGE = 60.0
RAC_WL_CUTOFF_HOURS = 0.5

# ─── Tatkal ───────────────────────────────────────────────────────────────────
# A CONFIRMED Tatkal / Premium Tatkal ticket earns no refund on cancellation.
# A WAITLISTED Tatkal ticket follows the normal WL clerkage rule.

TATKAL_QUOTAS: set[str] = {"TQ", "PT"}


class RefundRule(str, Enum):
    """Which deduction rule produced the breakdown — echoed to the client so
    the advisor can explain the number instead of just asserting it."""

    FLAT_CHARGE = "FLAT_CHARGE"  # > 48h: flat per-class charge
    PERCENT_25 = "PERCENT_25"  # 48h–12h: 25% of fare (min flat)
    PERCENT_50 = "PERCENT_50"  # 12h–4h: 50% of fare (min flat)
    NO_REFUND = "NO_REFUND"  # < 4h or post-chart
    TATKAL_NO_REFUND = "TATKAL_NO_REFUND"  # confirmed TQ/PT ticket
    CLERKAGE = "CLERKAGE"  # RAC/WL: flat clerkage
    ZERO_FARE = "ZERO_FARE"  # nothing was paid (e.g. child_free)


# ─── Refund Breakdown Dataclass ───────────────────────────────────────────────


@dataclass
class RefundBreakdown:
    """Refund outcome for one passenger — mirrors FareBreakdown's role."""

    fare: float
    deduction_amount: float
    refund_amount: float
    rule: str  # RefundRule value
    passenger_status: str  # "CNF" / "RAC" / "WL"

    def as_dict(self) -> dict:
        return {
            "fare": self.fare,
            "deduction_amount": self.deduction_amount,
            "refund_amount": self.refund_amount,
            "rule": self.rule,
            "passenger_status": self.passenger_status,
        }


# ─── Refund Calculator ────────────────────────────────────────────────────────


class RefundCalculator:
    """
    Stateless refund calculator — instantiate once, call calculate() many times.

    Usage:
        calculator = RefundCalculator()

        breakdown = calculator.calculate(
            fare=1450.0,
            passenger_status="CNF",
            train_class="3A",
            quota="GN",
            hours_to_departure=60.0,
        )
    """

    def calculate(
        self,
        *,
        fare: float,
        passenger_status: str,
        train_class: str,
        quota: str,
        hours_to_departure: float,
        is_chart_prepared: bool = False,
    ) -> RefundBreakdown:
        """
        Refund for one passenger if the ticket is cancelled `hours_to_departure`
        hours before the scheduled departure.

        Args:
            fare                — what this passenger actually paid (₹)
            passenger_status    — PassengerStatus value: "CNF" / "RAC" / "WL"
            train_class         — TrainClass value, e.g. "3A"
            quota               — Quota value, e.g. "GN", "TQ", "PT"
            hours_to_departure  — hours remaining until scheduled departure
            is_chart_prepared   — final chart done → online cancellation closed
        """
        if fare <= 0:
            return self._breakdown(fare, fare, RefundRule.ZERO_FARE, passenger_status)

        if passenger_status in ("RAC", "WL"):
            return self._rac_wl_refund(fare, passenger_status, hours_to_departure)

        return self._cnf_refund(
            fare, train_class, quota, hours_to_departure, is_chart_prepared
        )

    # ── Private helpers ───────────────────────────────────────────────────────

    def _rac_wl_refund(
        self, fare: float, passenger_status: str, hours_to_departure: float
    ) -> RefundBreakdown:
        """RAC/WL: flat clerkage up to 30 min before departure, then nothing."""
        if hours_to_departure < RAC_WL_CUTOFF_HOURS:
            return self._breakdown(fare, fare, RefundRule.NO_REFUND, passenger_status)

        deduction = min(CLERKAGE_CHARGE, fare)
        return self._breakdown(fare, deduction, RefundRule.CLERKAGE, passenger_status)

    def _cnf_refund(
        self,
        fare: float,
        train_class: str,
        quota: str,
        hours_to_departure: float,
        is_chart_prepared: bool,
    ) -> RefundBreakdown:
        if quota in TATKAL_QUOTAS:
            return self._breakdown(fare, fare, RefundRule.TATKAL_NO_REFUND, "CNF")

        if is_chart_prepared or hours_to_departure < CNF_HALF_MIN_HOURS:
            return self._breakdown(fare, fare, RefundRule.NO_REFUND, "CNF")

        flat_charge = float(
            FLAT_CANCELLATION_CHARGE.get(train_class, FLAT_CANCELLATION_CHARGE_DEFAULT)
        )

        if hours_to_departure >= CNF_FLAT_MIN_HOURS:
            deduction = flat_charge
            rule = RefundRule.FLAT_CHARGE
        elif hours_to_departure >= CNF_QUARTER_MIN_HOURS:
            deduction = max(fare * CNF_QUARTER_DEDUCTION_RATE, flat_charge)
            rule = RefundRule.PERCENT_25
        else:
            deduction = max(fare * CNF_HALF_DEDUCTION_RATE, flat_charge)
            rule = RefundRule.PERCENT_50

        deduction = min(round(deduction, 2), fare)
        return self._breakdown(fare, deduction, rule, "CNF")

    @staticmethod
    def _breakdown(
        fare: float, deduction: float, rule: RefundRule, passenger_status: str
    ) -> RefundBreakdown:
        return RefundBreakdown(
            fare=round(fare, 2),
            deduction_amount=round(deduction, 2),
            refund_amount=round(max(fare - deduction, 0.0), 2),
            rule=rule.value,
            passenger_status=passenger_status,
        )
