"""Enforces Constitution STD-11 (market-price & vig handling) as invariants."""
import math

from mlbmodel.market.oddsmath import (
    american_to_decimal, american_to_implied, prob_to_american, devig_two_way,
)


def test_american_implied_known_values():
    assert math.isclose(american_to_implied(-110), 110 / 210, rel_tol=1e-9)
    assert math.isclose(american_to_implied(+100), 0.5, rel_tol=1e-9)
    assert math.isclose(american_to_decimal(+150), 2.5, rel_tol=1e-9)
    assert math.isclose(american_to_decimal(-200), 1.5, rel_tol=1e-9)


def test_prob_american_roundtrip():
    # note: +100 / -100 both map to 0.5 (pick'em); the boundary is excluded as ambiguous.
    for odds in (-300, -150, -110, 110, 120, 250, 400):
        p = american_to_implied(odds)
        assert prob_to_american(p) == odds, (odds, p)


def test_implied_in_unit_interval():
    for odds in range(-500, 501, 7):
        if odds == 0:
            continue
        p = american_to_implied(odds)
        assert 0.0 < p < 1.0


def test_devig_sums_to_one():
    a, b = devig_two_way(american_to_implied(-130), american_to_implied(+110))
    assert math.isclose(a + b, 1.0, rel_tol=1e-12)
    assert 0 < a < 1 and 0 < b < 1
