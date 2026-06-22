import pytest
from app.core.fare_calculator import FareCalculator


@pytest.mark.parametrize(
    "distance_km, expected_rebate",
    [
        (50, 0.00),  # 0% slab ka aakhri km
        (51, 0.05),  # 5% slab ka pehla km  ← boundary
        (100, 0.05),  # 5% slab ka aakhri km
        (101, 0.15),  # 15% slab ka pehla km ← boundary
        (500, 0.15),
        (501, 0.25),  # ← boundary
        (1000, 0.25),
        (1001, 0.30),  # ← boundary
        (1500, 0.30),
        (1501, 0.40),  # ← boundary
        (2500, 0.40),
        (2501, 0.50),  # ← boundary
        (3500, 0.50),
        (3501, 0.55),  # open-ended top slab ← boundary
        (9999, 0.55),
    ],
)
def test_telescopic_rebate_slab_boundaries(distance_km, expected_rebate):
    assert FareCalculator._get_telescopic_rebate(distance_km) == expected_rebate


class FakeRule:
    train_class = "3A"
    base_fare_per_km = 1.0
    minimum_fare = 0
    reservation_charge = 30
    superfast_min_charge = 30
    tatkal_multiplier = 1.4
    gst_percent = 5
    premium_tatkal_min_multiplier = 1.5
    premium_tatkal_max_multiplier = 3.0


def test_basic_fare_100km_3a_general():
    calc = FareCalculator(fare_rule=FakeRule(), train_type="EXPRESS")
    fare = calc.calculate(distance_km=100, quota="GN")

    assert fare.base_fare == 95.0  # 100 × 0.95, ₹5 pe round
    assert fare.reservation_charge == 30.0
    assert fare.gst_amount == 4.75  # 95 × 5%
    assert fare.subtotal == 125.0  # 95 + 30
    assert fare.total_fare == 130.0  # 125 + 4.75, ₹1 pe round


def test_tatkal_charge():
    calc = FareCalculator(fare_rule=FakeRule(), train_type="EXPRESS")
    fare = calc.calculate(distance_km=100, quota="TQ")

    assert fare.is_tatkal is True
    assert fare.tatkal_charge == 38.0  # 95 × (1.4 - 1)
    assert fare.gst_amount == 6.65  # (95 + 38) × 5%
    assert fare.total_fare == 170.0


def test_superfast_uses_min_charge_when_30pct_is_lower():
    calc = FareCalculator(fare_rule=FakeRule(), train_type="RAJDHANI")
    fare = calc.calculate(distance_km=100, quota="GN")

    assert fare.is_superfast is True
    assert fare.superfast_charge == 30.0  # max(28.5, min_charge 30) → 30
    assert fare.total_fare == 161.0


def test_no_gst_on_non_ac_class():
    class SleeperRule(FakeRule):
        train_class = "SL"
        gst_percent = 0  # non-AC → no GST

    calc = FareCalculator(fare_rule=SleeperRule(), train_type="EXPRESS")
    fare = calc.calculate(distance_km=100, quota="GN")

    assert fare.gst_amount == 0.0
    assert fare.total_fare == 125.0  # 95 + 30, koi GST nahi


def test_child_under_5_is_free():
    calc = FareCalculator(fare_rule=FakeRule(), train_type="EXPRESS")
    fare = calc.calculate(distance_km=100, quota="GN", passenger_age=3)

    assert fare.concession_type == "child_free"
    assert fare.concession_amount == 95.0  # poora base kat gaya
