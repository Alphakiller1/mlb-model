"""
Canonical odds math (Constitution STD-11). Single source of truth consolidating the
copies currently duplicated across bet_evaluator.py / market_data.py / _compat.py /
sharp_tracker.py. Pure functions; the invariants are enforced by tests/test_oddsmath.py.
"""
from __future__ import annotations


def american_to_decimal(odds: int) -> float:
    return 1 + (odds / 100.0) if odds > 0 else 1 + (100.0 / -odds)


def american_to_implied(odds: int) -> float:
    return 100.0 / (odds + 100.0) if odds > 0 else (-odds) / (-odds + 100.0)


def prob_to_american(p: float) -> int:
    p = min(max(p, 1e-4), 1 - 1e-4)
    if p >= 0.5:
        return -round(100 * p / (1 - p))
    return round(100 * (1 - p) / p)


def devig_two_way(implied_a: float, implied_b: float) -> tuple[float, float]:
    """Remove the hold from a two-sided market; the two returned probs sum to 1."""
    total = implied_a + implied_b
    if total <= 0:
        raise ValueError("implied probabilities must be positive")
    return implied_a / total, implied_b / total
