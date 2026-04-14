"""
app/core/fare_calculator.py

Shared fare calculation utility — used by:
    - train/service.py       (fare enquiry endpoint)
    - booking/service.py     (fare at booking time)
    - cancellation/service.py (refund calculation)

All amounts are in INR (Indian Rupees).
Fare structure: Indian Railways IRCA table (01.01.2020, revised July 2025).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from math import ceil


# ─── Telescopic Rebate Slabs ──────────────────────────────────────────────────
# (min_km, max_km, rebate_percent)
# Longer the journey → lower the per-km rate.
# Source: IRCA fare table, effective 01.01.2020

_TELESCOPIC_SLABS: list[tuple[int, int | None, float]] = [
    (0, 50, 0.00),  # 0%  rebate
    (51, 100, 0.05),  # 5%  rebate
    (101, 500, 0.15),  # 15% rebate
    (501, 1000, 0.25),  # 25% rebate
    (1001, 1500, 0.30),  # 30% rebate
    (1501, 2500, 0.40),  # 40% rebate
    (2501, 3500, 0.50),  # 50% rebate
    (3501, None, 0.55),  # 55% rebate
]

# ─── Superfast train types ────────────────────────────────────────────────────
# These train types attract a superfast surcharge on top of base fare
_SUPERFAST_TRAIN_TYPES: set[str] = {
    "rajdhani",
    "shatabdi",
    "jan_shatabdi",
    "duronto",
    "garib_rath",
    "superfast",
}

# ─── IRCTC Online Service Charge ─────────────────────────────────────────────
_IRCTC_SERVICE_CHARGE = 15.0  # ₹15 + 5% GST = ₹15.75 (rounded to ₹16)
_IRCTC_SERVICE_CHARGE_GST = 0.05


# ─── Fare Breakdown Dataclass ────────────────────────────────────────────────


@dataclass
class FareBreakdown:
    """
    Complete fare breakdown for one passenger.
    Returned by FareCalculator.calculate() — used by both
    fare enquiry (show breakdown) and booking (store total_fare).
    """

    distance_km: int
    train_class: str
    quota: str

    # ── Components ────────────────────────────────────────────────────────────
    base_fare: float = 0.0  # after telescopic rebate + rounding
    reservation_charge: float = 0.0  # flat fee per class
    superfast_charge: float = 0.0  # 30% of base, min charge applies
    tatkal_charge: float = 0.0  # tatkal_multiplier × base - base
    concession_amount: float = 0.0  # senior citizen / child deduction
    gst_amount: float = 0.0  # 5% on AC classes only
    irctc_service_charge: float = 0.0  # online booking only

    # ── Flags ─────────────────────────────────────────────────────────────────
    is_superfast: bool = False
    is_tatkal: bool = False
    is_premium_tatkal: bool = False
    concession_type: str | None = (
        None  # "senior_citizen_male" / "senior_citizen_female" / "child"
    )

    @property
    def total_fare(self) -> float:
        """Final amount passenger pays — rounded to nearest ₹1."""
        total = (
            self.base_fare
            + self.reservation_charge
            + self.superfast_charge
            + self.tatkal_charge
            - self.concession_amount
            + self.gst_amount
            + self.irctc_service_charge
        )
        return round(total, 0)

    def as_dict(self) -> dict:
        return {
            "distance_km": self.distance_km,
            "train_class": self.train_class,
            "quota": self.quota,
            "base_fare": self.base_fare,
            "reservation_charge": self.reservation_charge,
            "superfast_charge": self.superfast_charge,
            "tatkal_charge": self.tatkal_charge,
            "concession_amount": self.concession_amount,
            "concession_type": self.concession_type,
            "gst_amount": self.gst_amount,
            "irctc_service_charge": self.irctc_service_charge,
            "total_fare": self.total_fare,
            "is_superfast": self.is_superfast,
            "is_tatkal": self.is_tatkal,
            "is_premium_tatkal": self.is_premium_tatkal,
        }


# ─── Fare Calculator ──────────────────────────────────────────────────────────


class FareCalculator:
    """
    Stateless fare calculator — instantiate once, call calculate() many times.

    Usage:
        calculator = FareCalculator(fare_rule, train_type)

        # Basic fare
        breakdown = calculator.calculate(distance_km=1386, quota="GN")

        # Tatkal fare
        breakdown = calculator.calculate(distance_km=1386, quota="TQ")

        # Senior citizen fare
        breakdown = calculator.calculate(
            distance_km=1386,
            quota="GN",
            passenger_age=65,
            passenger_gender="M",
        )

        # With IRCTC service charge (online booking)
        breakdown = calculator.calculate(
            distance_km=1386,
            quota="GN",
            include_irctc_charge=True,
        )
    """

    def __init__(self, fare_rule, train_type: str):
        """
        fare_rule — FareRules ORM object fetched from DB
        train_type — Trains.train_type value (e.g. "superfast", "express")
        """
        self._rule = fare_rule
        self._train_type = train_type.lower() if train_type else "unknown"

    # ── Public API ────────────────────────────────────────────────────────────

    def calculate(
        self,
        distance_km: int,
        quota: str,
        passenger_age: int | None = None,
        passenger_gender: str | None = None,  # "M" or "F"
        include_irctc_charge: bool = False,
        pt_multiplier: float | None = None,  # for Premium Tatkal dynamic pricing
    ) -> FareBreakdown:
        """
        Calculate complete fare for one passenger.

        Args:
            distance_km          — journey distance in km
            quota                — Quota enum value: "GN", "TQ", "PT" etc.
            passenger_age        — for concession calculation (optional)
            passenger_gender     — "M" or "F" for senior citizen rebate (optional)
            include_irctc_charge — True for online bookings
            pt_multiplier        — Premium Tatkal dynamic multiplier (1.0 to 3.0)
        """
        breakdown = FareBreakdown(
            distance_km=distance_km,
            train_class=self._rule.train_class,
            quota=quota,
        )

        # Step 1 — Base fare (telescopic rebate applied)
        breakdown.base_fare = self._calculate_base_fare(distance_km)

        # Step 2 — Superfast surcharge
        if self._is_superfast_train():
            breakdown.is_superfast = True
            breakdown.superfast_charge = self._calculate_superfast_charge(
                breakdown.base_fare
            )

        # Step 3 — Reservation charge (flat fee)
        breakdown.reservation_charge = float(self._rule.reservation_charge)

        # Step 4 — Tatkal / Premium Tatkal
        if quota == "TQ":
            breakdown.is_tatkal = True
            breakdown.tatkal_charge = self._calculate_tatkal_charge(breakdown.base_fare)
        elif quota == "PT":
            breakdown.is_premium_tatkal = True
            multiplier = pt_multiplier or self._rule.premium_tatkal_min_multiplier
            multiplier = max(
                self._rule.premium_tatkal_min_multiplier,
                min(multiplier, self._rule.premium_tatkal_max_multiplier),
            )
            breakdown.tatkal_charge = round(
                breakdown.base_fare * multiplier - breakdown.base_fare, 2
            )

        # Step 5 — Concession (senior citizen / child)
        if passenger_age is not None:
            concession = self._calculate_concession(
                breakdown.base_fare, passenger_age, passenger_gender
            )
            breakdown.concession_amount = concession["amount"]
            breakdown.concession_type = concession["type"]

        # Step 6 — GST (AC classes only, 5%)
        if self._rule.gst_percent > 0:
            taxable = (
                breakdown.base_fare
                + breakdown.superfast_charge
                + breakdown.tatkal_charge
            )
            breakdown.gst_amount = round(taxable * self._rule.gst_percent / 100, 2)

        # Step 7 — IRCTC service charge (online booking only)
        if include_irctc_charge:
            breakdown.irctc_service_charge = round(
                _IRCTC_SERVICE_CHARGE * (1 + _IRCTC_SERVICE_CHARGE_GST), 2
            )

        return breakdown

    # ── Private helpers ───────────────────────────────────────────────────────

    def _calculate_base_fare(self, distance_km: int) -> float:
        """
        Base fare = distance × per_km_rate × (1 - telescopic_rebate)
        Rounded to nearest ₹5, subject to minimum fare floor.
        """
        raw = distance_km * self._rule.base_fare_per_km

        # Apply telescopic rebate
        rebate = self._get_telescopic_rebate(distance_km)
        after_rebate = raw * (1 - rebate)

        # Round to nearest ₹5
        rounded = self._round_to_nearest_5(after_rebate)

        # Apply minimum fare floor
        return float(max(rounded, self._rule.minimum_fare))

    def _calculate_superfast_charge(self, base_fare: float) -> float:
        """
        Superfast surcharge = 30% of base fare.
        Subject to minimum charge per class.
        """
        charge = round(base_fare * 0.30, 2)
        return float(max(charge, self._rule.superfast_min_charge))

    def _calculate_tatkal_charge(self, base_fare: float) -> float:
        """
        Tatkal charge = (tatkal_multiplier - 1) × base_fare
        i.e. the additional amount on top of base fare.
        """
        return round(base_fare * (self._rule.tatkal_multiplier - 1), 2)

    def _calculate_concession(
        self,
        base_fare: float,
        age: int,
        gender: str | None,
    ) -> dict:
        """
        Concession rules:
            Senior citizen male   (≥60): 40% rebate on base fare
            Senior citizen female (≥58): 50% rebate on base fare
            Child 5-11 yrs              : 50% of base fare
            Child < 5 yrs               : free (no berth)
        Concession applied on base fare only — not on surcharges.
        """
        gender = (gender or "").upper()

        if age < 5:
            return {"amount": base_fare, "type": "child_free"}

        if 5 <= age <= 11:
            return {"amount": round(base_fare * 0.50, 2), "type": "child"}

        if age >= 60 and gender == "M":
            return {"amount": round(base_fare * 0.40, 2), "type": "senior_citizen_male"}

        if age >= 58 and gender == "F":
            return {
                "amount": round(base_fare * 0.50, 2),
                "type": "senior_citizen_female",
            }

        return {"amount": 0.0, "type": None}

    def _is_superfast_train(self) -> bool:
        return self._train_type in _SUPERFAST_TRAIN_TYPES

    @staticmethod
    def _get_telescopic_rebate(distance_km: int) -> float:
        for min_km, max_km, rebate in _TELESCOPIC_SLABS:
            if max_km is None or distance_km <= max_km:
                return rebate
        return 0.55  # fallback for very long journeys

    @staticmethod
    def _round_to_nearest_5(amount: float) -> int:
        """Round to nearest ₹5 — Indian Railways rounding rule."""
        return int(round(amount / 5) * 5)
